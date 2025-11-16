import cv2
from typing import List, Tuple, Optional
import numpy as np


def get_video_info(path: str):
    cap = cv2.VideoCapture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        duration = (count / fps) if fps > 0 else 0.0
        return fps, duration
    finally:
        cap.release()


def iterate_frames(path: str):
    """
    Iterate through video frames one by one (backward compatible)
    
    Args:
        path: Path to video file
        
    Yields:
        (frame_idx, frame) tuples
    """
    cap = cv2.VideoCapture(path)
    try:
        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame_idx, frame
            frame_idx += 1
    finally:
        cap.release()


def iterate_frames_batch(path: str, batch_size: int = 8, frame_skip: int = 2):
    """
    Iterate through video frames in batches (optimized for GPU processing)
    
    Args:
        path: Path to video file
        batch_size: Number of frames to process together
        frame_skip: Skip frames (1 = all frames, 2 = every 2nd frame, 3 = every 3rd frame, etc.)
        
    Yields:
        (batch_indices: List[int], batch_frames: List[np.ndarray]) tuples
    """
    cap = cv2.VideoCapture(path)
    # Tối ưu: set buffer size để giảm CPU overhead
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Giảm buffer để tránh lag
    
    try:
        frame_idx = 0
        batch = []
        batch_indices = []
        skipped_count = 0
        
        while True:
            ok, frame = cap.read()
            if not ok:
                # Yield remaining batch if any
                if batch:
                    yield batch_indices, batch
                break
            
            # Apply frame skip - chỉ lấy frame khi frame_idx chia hết cho frame_skip
            if frame_idx % frame_skip == 0:
                batch.append(frame)
                batch_indices.append(frame_idx)
                
                # Yield batch when full
                if len(batch) >= batch_size:
                    yield batch_indices, batch
                    batch = []
                    batch_indices = []
            else:
                skipped_count += 1
            
            frame_idx += 1
    finally:
        cap.release()


