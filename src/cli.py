import argparse
import os
import json
from datetime import datetime
from typing import Dict, Any

import yaml

from .detector import LicensePlateDetector
from .ocr import OcrEngine
from .matcher import is_match, normalize
from .videoio import iterate_frames, get_video_info
from .segmenter import SegmentAccumulator
from .concat import concat_segments
from .db import init_db, Video as DbVideo, Appearance as DbAppearance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plate', required=True, type=str)
    parser.add_argument('--video-dir', type=str)
    parser.add_argument('--output-dir', type=str)
    parser.add_argument('--conf', type=float, default=None)
    parser.add_argument('--nms', type=float, default=None)
    parser.add_argument('--match', type=str, default=None, choices=['exact', 'relaxed'])
    parser.add_argument('--max-dist', type=int, default=None)
    parser.add_argument('--lost', type=int, default=None)
    parser.add_argument('--pre-pad', type=float, default=None)
    parser.add_argument('--post-pad', type=float, default=None)
    parser.add_argument('--glob', type=str, default=None)
    parser.add_argument('--config', type=str)
    parser.add_argument('--annotate', action='store_true', help='Ghi video annotate với bbox và text')
    parser.add_argument('--ffmpeg', type=str, help='Đường dẫn ffmpeg.exe để concat nhanh')
    parser.add_argument('--db', type=str, default='db/vjts.sqlite', help='Đường dẫn file SQLite DB')
    args = parser.parse_args()

    # Load config YAML if provided
    cfg: Dict[str, Any] = {}
    if args.config and os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}

    def param(name: str, default):
        v = getattr(args, name)
        if v is not None:
            return v
        if name in cfg:
            return cfg[name]
        # nested keys support like cfg['model']['conf_threshold']
        nested = {
            'conf': ('model', 'conf_threshold'),
            'nms': ('model', 'nms_threshold'),
            'video_dir': ('video_dir',),
            'output_dir': ('output_dir',),
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

    video_dir = param('video_dir', None)
    output_dir = param('output_dir', None)
    conf = float(param('conf', 0.35))
    nms = float(param('nms', 0.5))
    match_mode = param('match', 'relaxed')
    max_dist = int(param('max_dist', 2))
    lost = int(param('lost', 10))
    pre_pad = float(param('pre_pad', 0.5))
    post_pad = float(param('post_pad', 0.5))

    if not video_dir or not output_dir:
        parser.error('--video-dir và --output-dir là bắt buộc nếu không cung cấp qua --config')

    os.makedirs(output_dir, exist_ok=True)

    detector = LicensePlateDetector(conf_threshold=conf)
    ocr_engine = OcrEngine(conf_threshold=0.60)
    Session = init_db(param('db', 'db/vjts.sqlite'))
    session = Session()

    segments = []

    for root, _, files in os.walk(video_dir):
        for name in files:
            if not name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                continue
            video_path = os.path.join(root, name)
            fps, duration = get_video_info(video_path)
            segmenter = SegmentAccumulator(fps=fps, lost_tolerance=lost)
            annotated_path = None

            writer = None
            if args.annotate:
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
                    is_matched_box = text and is_match(args.plate, text, match_mode, max_dist)
                    if args.annotate:
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
                    plate=normalize(args.plate),
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

    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    norm_plate = normalize(args.plate).replace('-', '')
    result_json_path = os.path.join(output_dir, f'VJTS_{norm_plate}_{timestamp}.json')
    with open(result_json_path, 'w', encoding='utf-8') as f:
        json.dump({ 'plate': args.plate, 'segments': segments }, f, ensure_ascii=False, indent=2)

    # Try to concat if possible (best-effort)
    try:
        output_video_path = os.path.join(output_dir, f'VJTS_{norm_plate}_{timestamp}.mp4')
        if segments:
            concat_segments(segments, output_video_path, ffmpeg_path=args.ffmpeg or None)
            print(f'Concatenated result saved to: {output_video_path}')
        else:
            print('No segments matched, skipping concat.')
    except Exception as e:
        print(f'Concat skipped due to error: {e}')

    print(f'Segments JSON saved to: {result_json_path}')
    session.close()


if __name__ == '__main__':
    main()


