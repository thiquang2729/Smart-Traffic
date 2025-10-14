import os
import json
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional

import yaml

from .detector import LicensePlateDetector
from .ocr import OcrEngine
from .matcher import is_match, normalize
from .videoio import iterate_frames, get_video_info
from .segmenter import SegmentAccumulator
from .concat import concat_segments
from .db import init_db, Video as DbVideo, Appearance as DbAppearance, Job as DbJob


def load_config(config_path: str | None) -> Dict[str, Any]:
    if not config_path or not os.path.exists(config_path):
        return {}
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def run_job(plate: str,
            video_dir: str,
            output_dir: str,
            config_path: str | None = None,
            annotate: bool = False,
            ffmpeg_path: str | None = None,
            db_path: str = 'db/vjts.sqlite',
            on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
            on_crop: Optional[Callable[[bytes], None]] = None) -> Dict[str, Any]:
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

    os.makedirs(output_dir, exist_ok=True)
    if on_event:
        on_event({'type': 'status', 'stage': 'start', 'video_dir': video_dir})

    detector = LicensePlateDetector(conf_threshold=conf)
    ocr_engine = OcrEngine(conf_threshold=0.60)
    Session = init_db(db_path)
    session = Session()

    segments: List[Dict[str, Any]] = []

    for root, _, files in os.walk(video_dir):
        for name in files:
            if not name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                continue
            video_path = os.path.join(root, name)
            fps, duration = get_video_info(video_path)
            segmenter = SegmentAccumulator(fps=fps, lost_tolerance=lost)
            annotated_path = None
            if on_event:
                on_event({'type': 'video_start', 'path': video_path, 'fps': fps, 'duration': duration})

            writer = None
            if annotate:
                import cv2
                os.makedirs(os.path.join(output_dir, 'annotated'), exist_ok=True)
                annotated_path = os.path.join(output_dir, 'annotated', os.path.splitext(name)[0] + '_annot.mp4')
                cap = cv2.VideoCapture(video_path)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(annotated_path, fourcc, max(fps, 1.0), (width, height))

            for frame_idx, frame in iterate_frames(video_path):
                boxes = detector.detect(frame)
                matched = False
                drawn_frame = frame
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
                    if annotate:
                        import cv2
                        color = (36, 255, 12) if is_matched_box else (255, 0, 0)
                        cv2.rectangle(drawn_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        if text:
                            cv2.putText(drawn_frame, text, (int(x1), max(0, int(y1) - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    if is_matched_box:
                        matched = True
                        break
                segmenter.update(frame_idx, matched)
                if writer is not None:
                    writer.write(drawn_frame)

            file_segments = segmenter.finalize()
            # persist video
            db_video = session.query(DbVideo).filter_by(path=video_path).one_or_none()
            if not db_video:
                db_video = DbVideo(path=video_path, fps=fps)
                session.add(db_video)
                session.commit()
            for s in file_segments:
                segments.append({
                    'video_path': annotated_path or video_path,
                    'start_time': max(0.0, s['start_time'] - pre_pad),
                    'end_time': min(duration, s['end_time'] + post_pad),
                })
                session.add(DbAppearance(
                    plate=normalize(plate),
                    camera_id=None,
                    video_id=db_video.video_id,
                    start_time=max(0.0, s['start_time'] - pre_pad),
                    end_time=min(duration, s['end_time'] + post_pad),
                    score_lp=None,
                    score_ocr=None,
                    match_mode=match_mode,
                ))
            session.commit()

            if writer is not None:
                writer.release()
            if on_event:
                on_event({'type': 'video_done', 'path': video_path, 'segments': len(file_segments)})

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


