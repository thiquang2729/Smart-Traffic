from typing import Optional, List
import function.helper as helper
import torch
import numpy as np
from .gpu_optimizer import get_device, get_gpu_info


class OcrEngine:
    def __init__(self, conf_threshold: float = 0.60, device: Optional[str] = None, use_gpu: bool = True):
        """
        Initialize OCR Engine
        
        Args:
            conf_threshold: Confidence threshold for OCR
            device: Device to use ('cuda' or 'cpu'). If None, auto-detect
            use_gpu: Whether to prefer GPU if available
        """
        # Auto-detect device if not specified
        if device is None:
            device = get_device(use_gpu=use_gpu)
        
        self.device = device
        print(f"🔧 OcrEngine using device: {device}")
        
        try:
            # Load model with device specification
            self.model = torch.hub.load(
                'yolov5', 
                'custom', 
                path='model/LP_ocr.pt', 
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
                    print(f"✅ OCR model loaded on GPU: {gpu_info['name']}")
                else:
                    print(f"✅ OCR model loaded on GPU")
        except RuntimeError as e:
            if 'out of memory' in str(e).lower():
                print(f"⚠️ GPU out of memory, falling back to CPU")
                torch.cuda.empty_cache()
                device = 'cpu'
                self.device = device
                self.model = torch.hub.load(
                    'yolov5', 
                    'custom', 
                    path='model/LP_ocr.pt', 
                    force_reload=False, 
                    source='local',
                    device=device
                )
                self.model.conf = conf_threshold
                self.model.eval()
            else:
                raise

    def read_text(self, roi) -> Optional[str]:
        """
        Read text from a single ROI (Region of Interest)
        
        Args:
            roi: ROI image (numpy array)
            
        Returns:
            Detected text or None
        """
        try:
            text = helper.read_plate(self.model, roi)
            if text and text != 'unknown':
                return text
            return None
        except RuntimeError as e:
            if 'out of memory' in str(e).lower():
                print(f"⚠️ GPU OOM during OCR, clearing cache and retrying...")
                torch.cuda.empty_cache()
                # Retry once
                text = helper.read_plate(self.model, roi)
                if text and text != 'unknown':
                    return text
                return None
            raise

    def read_text_batch(self, rois: List[np.ndarray]) -> List[Optional[str]]:
        """
        Read text from multiple ROIs (batch processing for GPU optimization)
        
        Note: This is a wrapper that processes sequentially since helper.read_plate
        doesn't support true batch processing. For better performance, consider
        modifying helper.read_plate to support batch processing.
        
        Args:
            rois: List of ROI images (numpy arrays)
            
        Returns:
            List of detected texts (None if not detected or 'unknown')
        """
        if not rois:
            return []
        
        texts = []
        for roi in rois:
            try:
                text = helper.read_plate(self.model, roi)
                if text and text != 'unknown':
                    texts.append(text)
                else:
                    texts.append(None)
            except RuntimeError as e:
                if 'out of memory' in str(e).lower():
                    print(f"⚠️ GPU OOM during batch OCR, clearing cache...")
                    torch.cuda.empty_cache()
                    # Retry
                    text = helper.read_plate(self.model, roi)
                    if text and text != 'unknown':
                        texts.append(text)
                    else:
                        texts.append(None)
                else:
                    texts.append(None)
        
        return texts


