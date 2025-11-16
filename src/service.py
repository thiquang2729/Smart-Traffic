import os
import json
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
import threading

import yaml

from .detector import LicensePlateDetector
from .ocr import OcrEngine
from .matcher import is_match, normalize
from .videoio import iterate_frames, iterate_frames_batch, get_video_info
from .segmenter import SegmentAccumulator
from .concat import concat_segments
from .db import init_db, Video as DbVideo, Appearance as DbAppearance, Job as DbJob
from .gpu_optimizer import get_optimal_batch_size, clear_gpu_cache, log_gpu_info, get_gpu_info
from .annotate import annotate_video_with_detections


def load_config(config_path: str | None) -> Dict[str, Any]:
    if not config_path or not os.path.exists(config_path):
        return {}
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


# Global cancellation flag storage
_cancellation_flags: Dict[str, threading.Event] = {}
_cancellation_lock = threading.Lock()


def get_cancellation_flag(job_id: str) -> threading.Event:
    """Get or create cancellation flag for a job"""
    with _cancellation_lock:
        if job_id not in _cancellation_flags:
            _cancellation_flags[job_id] = threading.Event()
        return _cancellation_flags[job_id]


def cancel_job(job_id: str) -> bool:
    """Cancel a running job"""
    with _cancellation_lock:
        if job_id in _cancellation_flags:
            _cancellation_flags[job_id].set()
            return True
        return False


def clear_cancellation_flag(job_id: str):
    """Clear cancellation flag after job completes"""
    with _cancellation_lock:
        _cancellation_flags.pop(job_id, None)


def run_job(plate: str,
            video_dir: str,
            output_dir: str,
            config_path: str | None = None,
            annotate: bool = False,
            ffmpeg_path: str | None = None,
            db_path: str = 'db/vjts.sqlite',
            on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
            on_crop: Optional[Callable[[bytes], None]] = None,
            cancellation_flag: Optional[threading.Event] = None) -> Dict[str, Any]:
    cfg = load_config(config_path)

    def param(name: str, default):
        # nested lookup helper
        nested = {
            'conf': ('model', 'conf_threshold'),
            'nms': ('model', 'nms_threshold'),
            'match': ('matching', 'mode'),
            'max_dist': ('matching', 'max_distance'),
            'lost': ('tracking', 'lost_tolerance'),
            'pre_pad': ('trim', 'pre_pad'),
            'post_pad': ('trim', 'post_pad'),
        }.get(name)
        if nested:
            cur = cfg
            for k in nested:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    cur = None
                    break
            if cur is not None:
                return cur
        return default

    conf = float(param('conf', 0.35))
    match_mode = param('match', 'relaxed')
    max_dist = int(param('max_dist', 2))
    lost = int(param('lost', 10))
    pre_pad = float(param('pre_pad', 0.5))
    post_pad = float(param('post_pad', 0.5))
    
    # GPU optimization parameters
    gpu_enabled = cfg.get('gpu', {}).get('enabled', True)
    gpu_batch_size = cfg.get('gpu', {}).get('batch_size', 8)
    auto_batch_size = cfg.get('gpu', {}).get('auto_batch_size', True)
    frame_skip = cfg.get('gpu', {}).get('frame_skip', 2)
    clear_cache_interval = cfg.get('gpu', {}).get('clear_cache_interval', 100)
    
    # Trajectory calibration (để tính tốc độ thực)
    pixel_to_meter = cfg.get('calibration', {}).get('pixel_to_meter', None)
    
    # Auto-calculate batch size if enabled
    if auto_batch_size and gpu_enabled:
        gpu_info = get_gpu_info()
        if gpu_info:
            # Use conservative mode để giảm CPU load
            optimal_batch = get_optimal_batch_size(gpu_info['total_memory_gb'], aggressive=False)
            if optimal_batch != gpu_batch_size:
                print(f"📊 Auto-adjusting batch size: {gpu_batch_size} -> {optimal_batch} (GPU: {gpu_info['total_memory_gb']:.1f}GB)")
                gpu_batch_size = optimal_batch
        else:
            # No GPU, use CPU mode
            gpu_enabled = False
            gpu_batch_size = 1
            frame_skip = 1
            print("⚠️ No GPU detected, using CPU mode")
    
    # Log settings
    if gpu_enabled:
        print(f"⚙️ GPU Settings: batch_size={gpu_batch_size}, frame_skip={frame_skip}, clear_cache_interval={clear_cache_interval}")
    
    # Log GPU info if enabled
    if gpu_enabled:
        log_gpu_info()

    os.makedirs(output_dir, exist_ok=True)
    if on_event:
        on_event({'type': 'status', 'stage': 'start', 'video_dir': video_dir})

    # Initialize models with GPU support
    detector = LicensePlateDetector(conf_threshold=conf, use_gpu=gpu_enabled)
    ocr_engine = OcrEngine(conf_threshold=0.60, use_gpu=gpu_enabled)
    Session = init_db(db_path)
    session = Session()

    segments: List[Dict[str, Any]] = []
    
    # Check cancellation at start
    if cancellation_flag and cancellation_flag.is_set():
        if on_event:
            on_event({'type': 'cancelled', 'message': 'Job đã bị hủy trước khi bắt đầu'})
        return {'error': 'cancelled', 'message': 'Job đã bị hủy'}

    for root, _, files in os.walk(video_dir):
        # Check cancellation before processing each video
        if cancellation_flag and cancellation_flag.is_set():
            if on_event:
                on_event({'type': 'cancelled', 'message': 'Job đã bị hủy'})
            break
            
        for name in files:
            if not name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                continue
            video_path = os.path.join(root, name)
            fps, duration = get_video_info(video_path)
            segmenter = SegmentAccumulator(fps=fps, lost_tolerance=lost, pixel_to_meter=pixel_to_meter, frame_skip=frame_skip)
            annotated_path = None
            if on_event:
                on_event({'type': 'video_start', 'path': video_path, 'fps': fps, 'duration': duration})

            # Lưu detection results để annotate sau
            detections_map = {}  # {frame_idx: [(x1, y1, x2, y2, text, is_matched), ...]}
            if annotate:
                os.makedirs(os.path.join(output_dir, 'annotated'), exist_ok=True)
                annotated_path = os.path.join(output_dir, 'annotated', os.path.splitext(name)[0] + '_annot.mp4')

            # Use batch processing if GPU is enabled
            if gpu_enabled and gpu_batch_size > 1:
                # Batch processing mode
                batch_num = 0
                frames_processed = 0
                
                for batch_indices, batch_frames in iterate_frames_batch(video_path, batch_size=gpu_batch_size, frame_skip=frame_skip):
                    # Check cancellation before each batch
                    if cancellation_flag and cancellation_flag.is_set():
                        if on_event:
                            on_event({'type': 'cancelled', 'message': 'Job đã bị hủy'})
                        break
                    
                    batch_num += 1
                    start_idx = batch_indices[0] if batch_indices else 0
                    end_idx = batch_indices[-1] if batch_indices else 0
                    
                    if on_event:
                        on_event({'type': 'progress', 'message': f'🚀 Processing batch {batch_num}, frames {start_idx}-{end_idx}'})
                    
                    # Batch detect
                    try:
                        batch_boxes = detector.detect_batch(batch_frames)
                    except RuntimeError as e:
                        if 'out of memory' in str(e).lower():
                            print(f"⚠️ GPU OOM, reducing batch size and retrying...")
                            clear_gpu_cache()
                            # Reduce batch size by half
                            new_batch_size = max(1, gpu_batch_size // 2)
                            print(f"⚠️ Retrying with batch size: {new_batch_size}")
                            # Process remaining frames with smaller batch
                            batch_boxes = []
                            for frame in batch_frames:
                                boxes = detector.detect(frame)
                                batch_boxes.append(boxes)
                        else:
                            raise
                    
                    # Process each frame in batch
                    # Tối ưu: giảm CPU overhead
                    for i, (frame_idx, frame, boxes) in enumerate(zip(batch_indices, batch_frames, batch_boxes)):
                        matched = False
                        matched_bbox = None  # Lưu bbox của biển số đã match để tính trajectory
                        frame_detections = []  # Lưu detections cho frame này
                        
                        # Process OCR - tối ưu để giảm CPU overhead
                        for (x1, y1, x2, y2, score) in boxes:
                            # Chỉ crop ROI khi cần
                            roi = frame[int(y1):int(y2), int(x1):int(x2)]
                            if roi.size == 0:  # Skip empty ROI
                                continue
                            
                            text = ocr_engine.read_text(roi)
                            is_matched_box = text and is_match(plate, text, match_mode, max_dist)
                            
                            if is_matched_box:
                                if on_crop:
                                    try:
                                        import cv2
                                        ok, buf = cv2.imencode('.jpg', roi)
                                        if ok:
                                            on_crop(bytes(buf))
                                    except Exception:
                                        pass
                                
                                matched = True
                                matched_bbox = (x1, y1, x2, y2)  # Lưu bbox để tính trajectory
                            
                            # Lưu detection để annotate sau
                            if annotate:
                                frame_detections.append((x1, y1, x2, y2, text or '', is_matched_box))
                            
                            if matched:
                                break
                        
                        # Lưu detections vào map
                        if annotate and frame_detections:
                            detections_map[frame_idx] = frame_detections
                        
                        # Update segmenter với bbox để tính trajectory
                        segmenter.update(frame_idx, matched, matched_bbox if matched else None)
                        
                        frames_processed += 1
                    
                    # Clear GPU cache periodically (less frequent to keep GPU busy)
                    if frames_processed % clear_cache_interval == 0:
                        clear_gpu_cache()
                        if on_event:
                            on_event({'type': 'progress', 'message': f'🧹 Cleared GPU cache at frame {frames_processed}'})
            else:
                # Single frame processing (CPU mode or batch_size=1)
                for frame_idx, frame in iterate_frames(video_path):
                    # Check cancellation before each frame
                    if cancellation_flag and cancellation_flag.is_set():
                        if on_event:
                            on_event({'type': 'cancelled', 'message': 'Job đã bị hủy'})
                        break
                    
                    boxes = detector.detect(frame)
                    matched = False
                    matched_bbox = None  # Lưu bbox để tính trajectory
                    frame_detections = []  # Lưu detections cho frame này
                    
                    for (x1, y1, x2, y2, score) in boxes:
                        roi = frame[int(y1):int(y2), int(x1):int(x2)]
                        text = ocr_engine.read_text(roi)
                        is_matched_box = text and is_match(plate, text, match_mode, max_dist)
                        
                        if on_event and frame_idx % 10 == 0:
                            on_event({'type': 'progress', 'frame': frame_idx, 'matched': bool(is_matched_box)})
                        
                        if is_matched_box and on_crop:
                            try:
                                import cv2
                                ok, buf = cv2.imencode('.jpg', roi)
                                if ok:
                                    on_crop(bytes(buf))
                            except Exception:
                                pass
                        
                        # Lưu detection để annotate sau
                        if annotate:
                            frame_detections.append((x1, y1, x2, y2, text or '', is_matched_box))
                        
                        if is_matched_box:
                            matched = True
                            matched_bbox = (x1, y1, x2, y2)  # Lưu bbox để tính trajectory
                            break
                    
                    # Lưu detections vào map
                    if annotate and frame_detections:
                        detections_map[frame_idx] = frame_detections
                    
                    segmenter.update(frame_idx, matched, matched_bbox if matched else None)

            file_segments = segmenter.finalize()
            
            # Tạo video annotated nếu có detections
            if annotate and detections_map:
                if on_event:
                    on_event({'type': 'progress', 'message': '🎨 Đang tạo video annotated...'})
                try:
                    annotate_video_with_detections(video_path, annotated_path, detections_map, fps)
                    print(f"✅ Video annotated đã được tạo: {annotated_path}")
                except Exception as e:
                    print(f"⚠️ Lỗi khi tạo video annotated: {e}")
                    annotated_path = None
            
            # persist video
            db_video = session.query(DbVideo).filter_by(path=video_path).one_or_none()
            if not db_video:
                db_video = DbVideo(path=video_path, fps=fps)
                session.add(db_video)
                session.commit()
            for s in file_segments:
                # Lấy trajectory data nếu có
                trajectory_data = s.get('trajectory', {})
                
                segments.append({
                    # Dùng video annotated nếu có (khi annotate=True), nếu không dùng video gốc
                    'video_path': annotated_path if annotated_path else video_path,
                    'start_time': max(0.0, s['start_time'] - pre_pad),
                    'end_time': min(duration, s['end_time'] + post_pad),
                    'trajectory': trajectory_data,  # Thêm trajectory vào segments
                })
                
                # Lưu vào database với trajectory data
                appearance = DbAppearance(
                    plate=normalize(plate),
                    camera_id=None,
                    video_id=db_video.video_id,
                    start_time=max(0.0, s['start_time'] - pre_pad),
                    end_time=min(duration, s['end_time'] + post_pad),
                    score_lp=None,
                    score_ocr=None,
                    match_mode=match_mode,
                )
                
                # Thêm trajectory data nếu có
                if trajectory_data:
                    appearance.speed_px_per_sec = trajectory_data.get('speed_px_per_sec')
                    appearance.speed_kmh = trajectory_data.get('speed_kmh')
                    appearance.direction_deg = trajectory_data.get('direction_deg')
                    appearance.direction_name = trajectory_data.get('direction_name')
                    appearance.total_distance_px = trajectory_data.get('total_distance_px')
                
                session.add(appearance)
            session.commit()
            
            if on_event:
                on_event({'type': 'video_done', 'path': video_path, 'segments': len(file_segments)})

    # Check if cancelled before finalizing
    if cancellation_flag and cancellation_flag.is_set():
        if on_event:
            on_event({'type': 'cancelled', 'message': 'Job đã bị hủy'})
        session.close()
        return {'error': 'cancelled', 'message': 'Job đã bị hủy', 'segments_count': len(segments)}
    
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    norm_plate = normalize(plate).replace('-', '')
    result_json_path = os.path.join(output_dir, f'VJTS_{norm_plate}_{timestamp}.json')
    with open(result_json_path, 'w', encoding='utf-8') as f:
        json.dump({ 'plate': plate, 'segments': segments }, f, ensure_ascii=False, indent=2)

    output_video_path = None
    if segments:
        try:
            output_video_path = os.path.join(output_dir, f'VJTS_{norm_plate}_{timestamp}.mp4')
            concat_segments(segments, output_video_path, ffmpeg_path=ffmpeg_path or None)
            if on_event:
                on_event({'type': 'concat_done', 'output': output_video_path})
        except Exception as e:
            output_video_path = None
            if on_event:
                on_event({'type': 'concat_error', 'message': str(e)})

    # persist job
    job_id = f"JOB-{norm_plate}-{timestamp}"
    session.add(DbJob(
        job_id=job_id,
        plate=normalize(plate),
        status='done',
        created_at=datetime.now(),
        finished_at=datetime.now(),
        result_video=output_video_path,
        segments_json=result_json_path,
    ))
    session.commit()
    session.close()

    if on_event:
        on_event({'type': 'done'})

    return {
        'job_id': job_id,
        'plate': plate,
        'segments_json': result_json_path,
        'result_video': output_video_path,
        'segments_count': len(segments),
        'segments': segments,  # Include segments for time sync
    }


