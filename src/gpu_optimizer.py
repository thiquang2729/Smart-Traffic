"""
GPU Optimization utilities for license plate detection
"""
import torch
from typing import Dict, Optional, Tuple


def get_device(use_gpu: bool = True) -> str:
    """
    Get the best available device (GPU or CPU)
    
    Args:
        use_gpu: Whether to prefer GPU
        
    Returns:
        'cuda' if GPU available and use_gpu=True, else 'cpu'
    """
    if use_gpu and torch.cuda.is_available():
        return 'cuda'
    return 'cpu'


def get_gpu_info() -> Optional[Dict[str, any]]:
    """
    Get GPU information including name, memory, and utilization
    
    Returns:
        Dict with GPU info or None if no GPU available
    """
    if not torch.cuda.is_available():
        return None
    
    try:
        device = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(device)
        
        # Get memory info
        total_memory = props.total_memory / 1e9  # GB
        allocated = torch.cuda.memory_allocated(device) / 1e9  # GB
        reserved = torch.cuda.memory_reserved(device) / 1e9  # GB
        
        return {
            'name': props.name,
            'total_memory_gb': total_memory,
            'allocated_memory_gb': allocated,
            'reserved_memory_gb': reserved,
            'free_memory_gb': total_memory - reserved,
            'device_id': device,
            'compute_capability': f"{props.major}.{props.minor}",
        }
    except Exception as e:
        print(f"⚠️ Warning: Could not get GPU info: {e}")
        return None


def get_optimal_batch_size(gpu_memory_gb: Optional[float] = None, model_size: str = 'medium', aggressive: bool = True) -> int:
    """
    Calculate optimal batch size based on GPU memory
    
    Args:
        gpu_memory_gb: GPU memory in GB (if None, will auto-detect)
        model_size: Model size hint ('small', 'medium', 'large')
        aggressive: If True, use larger batch sizes to maximize GPU utilization
        
    Returns:
        Optimal batch size
    """
    if gpu_memory_gb is None:
        gpu_info = get_gpu_info()
        if gpu_info:
            gpu_memory_gb = gpu_info['total_memory_gb']
        else:
            return 1  # CPU fallback
    
    # Heuristic: batch size based on GPU memory
    # Optimized for better GPU utilization - RTX 3050 4GB can handle batch_size=8-12
    if aggressive:
        # Aggressive mode: maximize GPU utilization
        if gpu_memory_gb >= 16:
            return 24  # RTX 3080, 3090, A4000, etc.
        elif gpu_memory_gb >= 8:
            return 16  # RTX 3070, 2080, etc.
        elif gpu_memory_gb >= 6:
            return 10  # GTX 1060, RTX 2060, etc.
        elif gpu_memory_gb >= 4:
            return 8   # RTX 3050, GTX 1050, etc. (4GB GPU - tăng lên 8 để GPU chạy hết công suất)
        else:
            return 2   # GPU nhỏ hơn
    else:
        # Conservative mode
        if gpu_memory_gb >= 16:
            return 16
        elif gpu_memory_gb >= 8:
            return 12
        elif gpu_memory_gb >= 6:
            return 6
        elif gpu_memory_gb >= 4:
            return 6
        else:
            return 1


def clear_gpu_cache():
    """Clear GPU cache to prevent memory leaks"""
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception as e:
            print(f"⚠️ Warning: Could not clear GPU cache: {e}")


def log_gpu_info():
    """Log GPU information for debugging"""
    gpu_info = get_gpu_info()
    if gpu_info:
        print(f"📊 GPU: {gpu_info['name']}")
        print(f"   Memory: {gpu_info['allocated_memory_gb']:.2f}/{gpu_info['total_memory_gb']:.2f} GB allocated")
        print(f"   Free: {gpu_info['free_memory_gb']:.2f} GB")
        print(f"   Compute Capability: {gpu_info['compute_capability']}")
    else:
        print("📊 No GPU available, using CPU")

