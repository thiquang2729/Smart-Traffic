from typing import Optional
import function.helper as helper
import torch


class OcrEngine:
    def __init__(self, conf_threshold: float = 0.60):
        # Reuse existing OCR yolov5 model and helper.read_plate
        self.model = torch.hub.load('yolov5', 'custom', path='model/LP_ocr.pt', force_reload=False, source='local')
        self.model.conf = conf_threshold

    def read_text(self, roi) -> Optional[str]:
        text = helper.read_plate(self.model, roi)
        if text and text != 'unknown':
            return text
        return None


