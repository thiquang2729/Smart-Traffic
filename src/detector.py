import torch
import os


class LicensePlateDetector:
    def __init__(self, conf_threshold: float = 0.35):
        # Reuse local yolov5 folder per project README
        self.model = torch.hub.load('yolov5', 'custom', path='model/LP_detector.pt', force_reload=False, source='local')
        self.model.conf = conf_threshold

    def detect(self, frame):
        results = self.model(frame, size=640)
        rows = results.pandas().xyxy[0].values.tolist()
        boxes = []
        for r in rows:
            x1, y1, x2, y2, conf = float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])
            boxes.append((x1, y1, x2, y2, conf))
        return boxes


