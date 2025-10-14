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
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

- Trình duyệt mở UI: `http://localhost:8000/ui/`
- Trang chủ API sẽ redirect sang UI.

### 4) Workflow sử dụng UI

- Nhập biển số, chọn thư mục video (mặc định `data/videos`) và thư mục output (`data/outputs`), bấm "Chạy thư mục" để chạy toàn bộ thư mục.
- Hoặc bấm "Upload + Chạy" để upload nhiều file video; UI sẽ bật realtime SSE, hiển thị log và crops liên tục.
- Giao diện có:
  - Khung video gốc (trên trái). Nếu >2 video gốc được chọn, có selector số phía dưới khung video để chuyển video.
  - Panel phải: nhập biển số, nút hành động, logs, vùng hiển thị crops.
  - Hàng dưới: Video gốc (trái) và video kết quả (phải) với thanh tua đồng bộ và Play/Pause cả hai video.

### 5) Các endpoint chính

- `POST /jobs` (Form): chạy theo thư mục

  - Form fields: `plate`, `video_dir` (default `data/videos`), `output_dir` (default `data/outputs`)
  - Response JSON chứa đường dẫn video kết quả nếu có: `result_video`

- `POST /upload` (Form): upload nhiều video, trả về `upload_dir`

  - Field: `files` (nhiều file)
  - Dùng `upload_dir` để theo dõi realtime bằng SSE

- `GET /events?plate=...&video_dir=...&output_dir=...` (SSE): stream tiến trình và crops

  - Event default: dữ liệu log (JSON/string)
  - Event `crop`: `data:image/jpeg;base64,...`
  - Event `result`: JSON chứa `result_video` khi xong

- `GET /download/result?path=...`: tải video kết quả

### 6) Chạy bằng CLI (không cần server)

```bash
python -m src.cli --plate "51G-123.45" --video-dir data/videos --output-dir data/outputs --annotate --config config/config.yaml --ffmpeg ./ffmpeg.exe
```

Các tham số hữu ích:

- `--match [exact|relaxed]` (mặc định `relaxed`)
- `--max-dist INT` (khoảng cách cho matching fuzzy)
- `--pre-pad FLOAT`, `--post-pad FLOAT` (đệm trước/sau đoạn match)

### 7) Demo nhanh (webcam, ảnh)

```bash
# webcam (nếu dùng module cũ)
python webcam.py

# ảnh
python lp_image.py -i test_image/3.jpg
```

### 8) Cấu trúc thư mục quan trọng

- `src/app.py`: FastAPI app, mount UI ở `/ui/`, endpoints `/jobs`, `/upload`, `/events`, `/download/result`
- `web/index.html`: UI web
- `model/`: trọng số detector/ocr
- `data/videos/`: chứa video đầu vào
- `data/outputs/`: nơi sinh JSON + mp4 kết quả
- `db/vjts.sqlite`: SQLite database

### 9) Lỗi thường gặp

- PowerShell không hỗ trợ `&&`/`||`: dùng `; if (...) {...} else {...}` khi chạy lệnh kết hợp.
- Thiếu FFmpeg: thêm `ffmpeg.exe` vào root (Windows) hoặc cài FFmpeg và chỉnh `--ffmpeg` hay PATH.
- Trình duyệt không hiển thị video kết quả: kiểm tra `result_video` tồn tại, quyền truy cập file, và đường dẫn khi tải qua `/download/result`.


## Installation

```bash
  git clone https://github.com/Marsmallotr/License-Plate-Recognition.git
  cd License-Plate-Recognition

  # install dependencies using pip 
  pip install -r ./requirement.txt
```

- **Pretrained model** provided in ./model folder in this repo 

- **Download yolov5 (old version) from this link:** [yolov5 - google drive](https://drive.google.com/file/d/1g1u7M4NmWDsMGOppHocgBKjbwtDA-uIu/view?usp=sharing)

- Copy yolov5 folder to project folder

## Run License Plate Recognition

```bash
  # run inference on webcam (15-20fps if there is 1 license plate in scene)
  python webcam.py 

  # run inference on image
  python lp_image.py -i test_image/3.jpg

  # run LP_recognition.ipynb if you want to know how model work in each step
```

## Result
![Demo 1](result/image.jpg)

![Vid](result/video_1.gif)

## Vietnamese Plate Dataset

This repo uses 2 sets of data for 2 stage of license plate recognition problem:

- [License Plate Detection Dataset](https://drive.google.com/file/d/1xchPXf7a1r466ngow_W_9bittRqQEf_T/view?usp=sharing)
- [Character Detection Dataset](https://drive.google.com/file/d/1bPux9J0e1mz-_Jssx4XX1-wPGamaS8mI/view?usp=sharing)

Thanks [Mì Ai](https://www.miai.vn/thu-vien-mi-ai/) and [winter2897](https://github.com/winter2897/Real-time-Auto-License-Plate-Recognition-with-Jetson-Nano/blob/main/doc/dataset.md) for sharing a part in this dataset.

## Training

**Training code for Yolov5:**

Use code in ./training folder
```bash
  training/Plate_detection.ipynb     #for LP_Detection
  training/Letter_detection.ipynb    #for Letter_detection
```
