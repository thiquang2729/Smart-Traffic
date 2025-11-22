"""
Trajectory analysis: tính tốc độ và hướng di chuyển của biển số
"""
import numpy as np
from typing import List, Tuple, Dict, Optional


def calculate_speed_and_direction(
    trajectory: List[Tuple[float, float, float]],  # [(frame_idx, center_x, center_y), ...]
    fps: float,
    pixel_to_meter: Optional[float] = None  # Optional: để convert sang km/h
) -> Dict[str, float]:
    """
    Tính tốc độ và hướng di chuyển từ trajectory.
    
    Args:
        trajectory: List of (frame_idx, center_x, center_y)
        fps: Frames per second của video
        pixel_to_meter: Tỷ lệ chuyển đổi pixel -> meter (nếu có calibration)
    
    Returns:
        Dict với các metrics: speed_px_per_sec, speed_kmh, direction_deg, total_distance, etc.
    """
    if len(trajectory) < 2:
        return {
            'speed_px_per_sec': 0.0,
            'speed_kmh': None,
            'direction_deg': 0.0,
            'direction_name': 'Không xác định',
            'total_distance_px': 0.0,
            'total_distance_m': None,
            'avg_acceleration_px_per_sec2': 0.0,
            'max_speed_px_per_sec': 0.0,
            'min_speed_px_per_sec': 0.0
        }
    
    speeds_px_per_sec = []
    directions_deg = []
    distances_px = []
    accelerations = []
    
    prev_speed = None
    
    for i in range(1, len(trajectory)):
        frame1, x1, y1 = trajectory[i-1]
        frame2, x2, y2 = trajectory[i]
        
        # Tính khoảng cách pixel
        dx = x2 - x1
        dy = y2 - y1
        distance_px = np.sqrt(dx**2 + dy**2)
        distances_px.append(distance_px)
        
        # Tính thời gian (giây)
        time_diff_sec = (frame2 - frame1) / fps
        
        if time_diff_sec > 0:
            # Tốc độ (pixel/giây)
            speed_px_per_sec = distance_px / time_diff_sec
            speeds_px_per_sec.append(speed_px_per_sec)
            
            # Hướng di chuyển (độ, 0° = phải, 90° = lên, 180° = trái, 270° = xuống)
            # Lưu ý: trong image coordinate, y tăng xuống dưới
            direction_rad = np.arctan2(-dy, dx)  # -dy vì y tăng xuống dưới trong image
            direction_deg = np.degrees(direction_rad)
            # Normalize về 0-360
            if direction_deg < 0:
                direction_deg += 360
            directions_deg.append(direction_deg)
            
            # Gia tốc (nếu có)
            if prev_speed is not None and time_diff_sec > 0:
                acceleration = (speed_px_per_sec - prev_speed) / time_diff_sec
                accelerations.append(acceleration)
            prev_speed = speed_px_per_sec
    
    # Tính toán tổng hợp
    total_distance_px = sum(distances_px)
    avg_speed_px_per_sec = np.mean(speeds_px_per_sec) if speeds_px_per_sec else 0.0
    max_speed_px_per_sec = np.max(speeds_px_per_sec) if speeds_px_per_sec else 0.0
    min_speed_px_per_sec = np.min(speeds_px_per_sec) if speeds_px_per_sec else 0.0
    
    # Chuyển đổi sang km/h (nếu có calibration)
    speed_kmh = None
    total_distance_m = None
    if pixel_to_meter:
        # pixel/giây -> meter/giây -> km/h
        speed_ms = avg_speed_px_per_sec * pixel_to_meter
        speed_kmh = speed_ms * 3.6  # m/s -> km/h
        total_distance_m = total_distance_px * pixel_to_meter
    
    # Hướng trung bình (cần xử lý đặc biệt vì góc có tính tuần hoàn)
    if directions_deg:
        # Chuyển về vector để tính trung bình
        dir_radians = [np.radians(d) for d in directions_deg]
        avg_x = np.mean([np.cos(r) for r in dir_radians])
        avg_y = np.mean([np.sin(r) for r in dir_radians])
        avg_direction_deg = np.degrees(np.arctan2(avg_y, avg_x))
        if avg_direction_deg < 0:
            avg_direction_deg += 360
    else:
        avg_direction_deg = 0.0
    
    # Gia tốc trung bình
    avg_acceleration = np.mean(accelerations) if accelerations else 0.0
    
    result = {
        'speed_px_per_sec': float(avg_speed_px_per_sec),
        'max_speed_px_per_sec': float(max_speed_px_per_sec),
        'min_speed_px_per_sec': float(min_speed_px_per_sec),
        'direction_deg': float(avg_direction_deg),
        'direction_name': _direction_to_name(avg_direction_deg),
        'total_distance_px': float(total_distance_px),
        'total_distance_m': float(total_distance_m) if total_distance_m else None,
        'avg_acceleration_px_per_sec2': float(avg_acceleration),
        'trajectory_length': len(trajectory),
        'duration_sec': (trajectory[-1][0] - trajectory[0][0]) / fps if len(trajectory) > 1 else 0.0
    }
    
    if speed_kmh is not None:
        result['speed_kmh'] = float(speed_kmh)
        result['max_speed_kmh'] = float(max_speed_px_per_sec * pixel_to_meter * 3.6)
    
    return result


def _direction_to_name(deg: float) -> str:
    """Chuyển góc độ thành tên hướng"""
    if 337.5 <= deg or deg < 22.5:
        return "Đông"
    elif 22.5 <= deg < 67.5:
        return "Đông Bắc"
    elif 67.5 <= deg < 112.5:
        return "Bắc"
    elif 112.5 <= deg < 157.5:
        return "Tây Bắc"
    elif 157.5 <= deg < 202.5:
        return "Tây"
    elif 202.5 <= deg < 247.5:
        return "Tây Nam"
    elif 247.5 <= deg < 292.5:
        return "Nam"
    elif 292.5 <= deg < 337.5:
        return "Đông Nam"
    return "Không xác định"

