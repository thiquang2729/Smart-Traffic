class SegmentAccumulator:
    def __init__(self, fps: float, lost_tolerance: int = 10):
        self.fps = fps if fps and fps > 0 else 25.0
        self.lost_tolerance = max(1, int(lost_tolerance))
        self.in_segment = False
        self.last_seen_frame = -1
        self.start_frame = -1
        self.segments = []

    def update(self, frame_idx: int, matched: bool):
        if matched:
            if not self.in_segment:
                self.in_segment = True
                self.start_frame = frame_idx
            self.last_seen_frame = frame_idx
        else:
            if self.in_segment and (frame_idx - self.last_seen_frame) > self.lost_tolerance:
                end_frame = self.last_seen_frame
                self._push_segment(self.start_frame, end_frame)
                self.in_segment = False
                self.start_frame = -1
                self.last_seen_frame = -1

    def finalize(self):
        if self.in_segment and self.last_seen_frame >= 0 and self.start_frame >= 0:
            self._push_segment(self.start_frame, self.last_seen_frame)
            self.in_segment = False
        return self.segments

    def _push_segment(self, start_f: int, end_f: int):
        self.segments.append({
            'start_time': start_f / self.fps,
            'end_time': end_f / self.fps,
        })


