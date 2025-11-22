import torch
import os
from typing import List, Optional
from .gpu_optimizer import get_device, get_gpu_info


class LicensePlateDetector:
    def __init__(self, conf_threshold: float = 0.35, device: Optional[str] = None, use_gpu: bool = True):
        """
        Initialize License Plate Detector
        
        Args:
            conf_threshold: Confidence threshold for detection
            device: Device to use ('cuda' or 'cpu'). If None, auto-detect
            use_gpu: Whether to prefer GPU if available
        """
        # Auto-detect device if not specified
        if device is None:
            device = get_device(use_gpu=use_gpu)
        
        self.device = device
        print(f"🔧 LicensePlateDetector using device: {device}")
        
        try:
            # Load model with device specification
            self.model = torch.hub.load(
                'yolov5', 
                'custom', 
                path='model/LP_detector.pt', 
                force_reload=False, 
                source='local',
                device=device
            )
            self.model.conf = conf_threshold
            
            # Ensure model is in eval mode
            self.model.eval()
            
            # Move to device explicitly if needed
            if device == 'cuda' and torch.cuda.is_available():
                self.model = self.model.to(device)
                gpu_info = get_gpu_info()
                if gpu_info:
                    print(f"✅ Model loaded on GPU: {gpu_info['name']}")
                else:
                    print(f"✅ Model loaded on GPU")
        except RuntimeError as e:
            if 'out of memory' in str(e).lower():
                print(f"⚠️ GPU out of memory, falling back to CPU")
                torch.cuda.empty_cache()
                device = 'cpu'
                self.device = device
                self.model = torch.hub.load(
                    'yolov5', 
                    'custom', 
                    path='model/LP_detector.pt', 
                    force_reload=False, 
                    source='local',
                    device=device
                )
                self.model.conf = conf_threshold
                self.model.eval()
            else:
                raise

    def detect(self, frame):
        """
        Detect license plates in a single frame
        
        Args:
            frame: Input frame (numpy array, BGR format)
            
        Returns:
            List of (x1, y1, x2, y2, confidence) tuples
        """
        try:
            results = self.model(frame, size=640)
            rows = results.pandas().xyxy[0].values.tolist()
            boxes = []
            for r in rows:
                x1, y1, x2, y2, conf = float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])
                boxes.append((x1, y1, x2, y2, conf))
            return boxes
        except RuntimeError as e:
            if 'out of memory' in str(e).lower():
                print(f"⚠️ GPU OOM during detection, clearing cache and retrying...")
                torch.cuda.empty_cache()
                # Retry once
                results = self.model(frame, size=640)
                rows = results.pandas().xyxy[0].values.tolist()
                boxes = []
                for r in rows:
                    x1, y1, x2, y2, conf = float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])
                    boxes.append((x1, y1, x2, y2, conf))
                return boxes
            raise

    def detect_batch(self, frames: List) -> List[List]:
        """
        Detect license plates in multiple frames (batch processing for GPU optimization)
        
        Args:
            frames: List of frames (numpy arrays, BGR format)
            
        Returns:
            List of detection results, each is a list of (x1, y1, x2, y2, confidence) tuples
        """
        if not frames:
            return []
        
        try:
            # YOLOv5 automatically handles batch processing
            results = self.model(frames, size=640)
            
            # Parse results for each frame in batch
            all_boxes = []
            for i in range(len(frames)):
                rows = results.pandas().xyxy[i].values.tolist()
                boxes = []
                for r in rows:
                    x1, y1, x2, y2, conf = float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])
                    boxes.append((x1, y1, x2, y2, conf))
                all_boxes.append(boxes)
            
            return all_boxes
        except RuntimeError as e:
            if 'out of memory' in str(e).lower():
                print(f"⚠️ GPU OOM during batch detection, clearing cache...")
                torch.cuda.empty_cache()
                # Fallback: process one by one
                print(f"⚠️ Falling back to single frame processing")
                all_boxes = []
                for frame in frames:
                    boxes = self.detect(frame)
                    all_boxes.append(boxes)
                return all_boxes
            raise


