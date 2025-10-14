# Vietnamese License Plate Recognition

This repository provides you with a detailed guide on how to training and build a Vietnamese License Plate detection and recognition system. This system can work on 2 types of license plate in Vietnam, 1 line plates and 2 lines plates.

## Quick Start (VJTS UI + API)

### 1) Requirements

- Python 3.9+ (khuyến nghị 3.10/3.11)
- Windows (có kèm `ffmpeg.exe` trong root dự án) hoặc tự cài FFmpeg và thêm vào PATH
- GPU là tùy chọn; CPU vẫn chạy nhưng chậm hơn

### 2) Cài đặt

```bash
pip install -r requirement.txt
```

Lưu ý: Models đã có sẵn ở `model/`. Thư mục dữ liệu mẫu ở `data/videos/`. File cấu hình ở `config/config.yaml`.

### 3) Chạy server API + UI web

```bash
python -m uvicorn src.app:app --host localhost --port 8000 --reload
```

### 4) Workflow sử dụng UI

- Nhập biển số, chọn thư mục video (mặc định `data/videos`) và thư mục output (`data/outputs`), bấm "Chạy thư mục" để chạy toàn bộ thư mục.
- Hoặc bấm "Upload + Chạy" để upload nhiều file video; UI sẽ bật realtime SSE, hiển thị log và crops liên tục.
- Giao diện có:
  - Khung video gốc (trên trái). Nếu >2 video gốc được chọn, có selector số phía dưới khung video để chuyển video.
  - Panel phải: nhập biển số, nút hành động, logs, vùng hiển thị crops.
  - Hàng dưới: Video gốc (trái) và video kết quả (phải) với thanh tua đồng bộ và Play/Pause cả hai video.






```



```
