"""
Annotate video with detection results
"""
import cv2
from typing import Dict, List, Tuple
import os


def annotate_video_with_detections(
    video_path: str,
    output_path: str,
    detections: Dict[int, List[Tuple[float, float, float, float, str, bool]]],  # frame_idx -> [(x1, y1, x2, y2, text, is_matched), ...]
    fps: float = 25.0
):
    """
    Annotate video with detection results
    
    Args:
        video_path: Path to original video
        output_path: Path to save annotated video
        detections: Dict mapping frame_idx to list of (x1, y1, x2, y2, text, is_matched)
        fps: Video FPS
    """
    cap = cv2.VideoCapture(video_path)
    
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            
            # Annotate frame if has detections
            if frame_idx in detections:
                for (x1, y1, x2, y2, text, is_matched) in detections[frame_idx]:
                    color = (36, 255, 12) if is_matched else (255, 0, 0)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    if text:
                        cv2.putText(frame, text, (int(x1), max(0, int(y1) - 10)), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            writer.write(frame)
            frame_idx += 1
        
        writer.release()
    finally:
        cap.release()

