from typing import Optional, Tuple, Dict


class SegmentAccumulator:
    def __init__(self, fps: float, lost_tolerance: int = 10, pixel_to_meter: Optional[float] = None, frame_skip: int = 1):
        self.fps = fps if fps and fps > 0 else 25.0
        self.lost_tolerance = max(1, int(lost_tolerance))
        self.in_segment = False
        self.last_seen_frame = -1
        self.start_frame = -1
        self.segments = []
        self.pixel_to_meter = pixel_to_meter
        self.frame_skip = max(1, int(frame_skip))  # Lưu frame_skip để điều chỉnh start_frame
        
        # Trajectory tracking: lưu tọa độ center của biển số qua các frame
        self.current_trajectory = []  # [(frame_idx, center_x, center_y), ...]

    def update(self, frame_idx: int, matched: bool, bbox: Optional[Tuple[float, float, float, float]] = None):
        """
        Update segment accumulator
        
        Args:
            frame_idx: Frame index
            matched: Whether plate matched
            bbox: Optional bounding box (x1, y1, x2, y2) để tính trajectory
        """
        if matched:
            # Tính center point nếu có bbox
            if bbox:
                x1, y1, x2, y2 = bbox
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                self.current_trajectory.append((frame_idx, center_x, center_y))
            
            if not self.in_segment:
                self.in_segment = True
                # Bắt đầu segment từ frame phát hiện biển số lần đầu
                # Sử dụng frame_idx thực tế (không điều chỉnh) để cắt chính xác
                self.start_frame = frame_idx
                print(f"🟢 Segment started at frame {frame_idx} ({frame_idx / self.fps:.2f}s)")
            self.last_seen_frame = frame_idx
        else:
            # Kiểm tra lost_tolerance: tính số frame được xử lý (không phải frame thực tế)
            # Với frame_skip, khoảng cách giữa các frame được xử lý = frame_skip
            # Ví dụ: frame_skip=3, lost_tolerance=10 → mất 10 frame được xử lý = 30 frame thực tế
            if self.in_segment:
                # Tính số frame được xử lý đã mất
                frames_processed_lost = (frame_idx - self.last_seen_frame) // self.frame_skip
                if frames_processed_lost > self.lost_tolerance:
                    # Kết thúc segment tại frame cuối cùng phát hiện biển số
                    end_frame = self.last_seen_frame
                    print(f"🔴 Segment ended at frame {end_frame} ({end_frame / self.fps:.2f}s), lost {frames_processed_lost} processed frames")
                    # Phân tích trajectory trước khi kết thúc segment
                    trajectory_data = self._analyze_trajectory(self.pixel_to_meter)
                    self._push_segment(self.start_frame, end_frame, trajectory_data)
                    self.in_segment = False
                    self.start_frame = -1
                    self.last_seen_frame = -1
                    self.current_trajectory = []

    def _analyze_trajectory(self, pixel_to_meter: Optional[float] = None) -> Dict:
        """Phân tích trajectory của segment hiện tại"""
        if len(self.current_trajectory) < 2:
            return {}
        
        from .trajectory import calculate_speed_and_direction
        return calculate_speed_and_direction(self.current_trajectory, self.fps, pixel_to_meter)

    def finalize(self):
        if self.in_segment and self.last_seen_frame >= 0 and self.start_frame >= 0:
            trajectory_data = self._analyze_trajectory(self.pixel_to_meter)
            self._push_segment(self.start_frame, self.last_seen_frame, trajectory_data)
            self.in_segment = False
        return self.segments

    def _push_segment(self, start_f: int, end_f: int, trajectory_data: Dict = None):
        start_time = start_f / self.fps
        end_time = end_f / self.fps
        segment = {
            'start_time': start_time,
            'end_time': end_time,
        }
        if trajectory_data:
            segment['trajectory'] = trajectory_data
        
        # Log để debug
        print(f"📍 Segment created: frame {start_f} ({start_time:.2f}s) → frame {end_f} ({end_time:.2f}s), duration: {end_time - start_time:.2f}s")
        
        self.segments.append(segment)


