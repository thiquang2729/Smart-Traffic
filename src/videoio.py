import cv2


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


