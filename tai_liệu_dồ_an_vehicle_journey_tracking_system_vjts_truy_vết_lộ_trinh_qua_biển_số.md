# Vehicle Journey Tracking System (VJTS)

**Đồ án: Hệ thống Truy vết Lộ trình Phương tiện qua Biển số xe từ Camera Giao thông**

---

## 0. Tóm tắt điều hành (Executive Summary)
VJTS là hệ thống cho phép nhập **biển số** cần truy vết, quét qua **kho video** mô phỏng mạng lưới camera giao thông để **phát hiện, OCR, theo dõi, cắt clip** mỗi lần xe xuất hiện và **ghép** các đoạn theo **thứ tự thời gian**, tạo ra **một video tổng hợp** lộ trình di chuyển.

**Đầu vào:** Biển số (text), danh sách file video (từ nhiều camera).  
**Xử lý:** Phát hiện biển số (detector), OCR, tracking, cắt/ghép video.  
**Đầu ra:** 1 file `.mp4` tổng hợp.

MVP tập trung xử lý offline trên bộ video đã có. Bản mở rộng có thể bổ sung **metadata DB**, API web, giao diện UI.

---

## 1. Tổng quan Dự án (Project Overview)
### 1.1 Mục tiêu
- Xây dựng pipeline **tự động** từ nhập biển số → quét kho video → phát hiện & OCR → theo dõi → trích xuất đoạn → ghép → trả về video tổng hợp.
- Đảm bảo **độ chính xác** phát hiện/OCR đủ tốt cho demo đồ án (≥90% precision với tập video mẫu), **tính lặp lại** và **dễ chạy**.

### 1.2 Phạm vi (Scope)
- **MVP (bắt buộc):**
  - Nhập biển số (chuẩn VN, ví dụ `51G-123.45`).
  - Duyệt thư mục video (nhiều camera) theo batch.
  - Phát hiện biển số + OCR + so khớp chuỗi (khoan dung sai nhỏ do OCR).
  - Xác định `start_time`, `end_time` mỗi lần xuất hiện.
  - Cắt & ghép các đoạn theo thời gian.
- **Stretch (khuyến khích):**
  - DB metadata (SQLite) để cache lần xuất hiện, tăng tốc truy vấn lại.
  - API (FastAPI) + UI web đơn giản.
  - Theo dõi liên camera (ước lượng thời gian/đường đi bằng timestamp & camera_id).

### 1.3 Giả định & Ràng buộc
- Video đầu vào có **timestamp** tin cậy (từ tên file hoặc metadata).  
- Biển số xuất hiện **rõ đủ** (độ phân giải tối thiểu ~720p, không quá mờ/che).  
- Hệ thống chạy offline trên máy cá nhân, **CPU** + (tùy chọn) **GPU** nếu có.

---

## 2. Kiến trúc Hệ thống (System Architecture)
### 2.1 Sơ đồ module (mô tả chữ)
```
UI (Web/Desktop/CLI)
    ↓
Video Management (nạp danh sách video, đọc frame, chuẩn hóa FPS)
    ↓
Processing Core
  ├─ License Plate Detector (YOLOv8/YOLOv5, mô hình LP)
  ├─ OCR (EasyOCR/PaddleOCR)
  ├─ Tracking Engine (SORT/DeepSORT/ByteTrack hoặc tracking IOU + heuristic)
  └─ Matching & Segmenter (khớp biển số, tạo segment start/end)
    ↓
Video Processor (trim bằng MoviePy/FFmpeg, concat)
    ↓
Output (.mp4)

(Phụ trợ) Metadata DB (SQLite): cameras, videos, appearances, jobs
```

### 2.2 Lựa chọn công nghệ
- **Python 3.9+**
- **OpenCV**: đọc/ghi video, xử lý ảnh, vẽ bbox.
- **ultralytics (YOLOv8)** hoặc **YOLOv5** cho **detector biển số**.
- **EasyOCR** hoặc **PaddleOCR** cho OCR.
- **MoviePy** (hoặc **FFmpeg** qua subprocess) để **cắt/ghép**.
- **FastAPI**/**Flask** cho API & UI web;
- **SQLite** cho metadata (tùy chọn); **SQLAlchemy** ORM.
- **pydantic** cho cấu hình.

### 2.3 Cấu hình & tham số chính
- `CONF_THRESHOLD` (ví dụ 0.25–0.5) cho detector.  
- `NMS_THRESHOLD` (ví dụ 0.4–0.6).  
- `OCR_LANGS` (ví dụ `['en']`), `OCR_DETAIL_LEVEL`.  
- `PLATE_MATCH_MODE`: exact / relaxed (cho phép Levenshtein distance ≤1–2).  
- `TRACK_LOST_TOLERANCE`: số frame cho phép mất tạm thời.  
- `TRIM_PADDING`: đệm trước/sau (giây) khi cắt đoạn.

---

## 3. Luồng hoạt động chi tiết (Detailed Workflow)
### 3.1 Nhập liệu
1) Người dùng nhập **biển số mục tiêu**.  
2) Chỉ định **thư mục chứa video** (mỗi file là 1 camera/time slot) và (tùy chọn) file cấu hình.

### 3.2 Quét & đọc video
- Liệt kê `video_list = glob(video_dir, *.mp4|*.avi|*.mov)`.  
- Với mỗi `video_path`:
  - Mở bằng OpenCV/MoviePy, chuẩn hóa FPS nếu cần (ví dụ 25/30).  
 

### 3.3 Phát hiện & OCR
- Chạy **detector LP** → danh sách bbox (x1,y1,x2,y2) + score.  
- Lọc theo score, cắt roi từng biển số; tiền xử lý (grayscale, resize, sharpen) rồi **OCR**.  
- Chuẩn hóa chuỗi OCR (remove space, thay `O↔0`, `I↔1`, upper-case, bỏ `-`/`.`).

### 3.4 So khớp & Theo dõi
- So khớp chuỗi OCR với **biển số mục tiêu** theo `PLATE_MATCH_MODE`:
  - **exact**: trùng 100% sau chuẩn hóa.  
  - **relaxed**: khoảng cách Levenshtein ≤ 1–2; thêm luật định dạng biển số VN (2–3 ký tự chữ + số).
- Khi khớp lần đầu trong video: ghi `start_time = frame_idx / fps`.  
- Duy trì **tracking** bằng:
  - **IOU matching** giữa bbox frame t và t+1 (đơn giản & nhanh), hoặc  
  - **SORT/DeepSORT/ByteTrack** (ổn định hơn khi đông xe).
- Khi biển số mất liên tục > `TRACK_LOST_TOLERANCE`:
  - xác nhận **kết thúc segment**: `end_time` ở frame cuối có khớp.  
  - Lưu bản ghi: `(camera_id, video_path, start_time, end_time)`.

### 3.5 Trích xuất & Ghép
- Sau khi quét hết video → danh sách **segments**.  
- Chuẩn hóa thời gian tuyệt đối (từ filename/metadata) để **sắp xếp**.  
- **Cắt** mỗi đoạn bằng MoviePy `subclip(start_time-PADDING, end_time+PADDING)` (clamp [0,duration]).  
- **Ghép** theo thứ tự thời gian bằng `concatenate_videoclips` (re-encode) hoặc FFmpeg concat demuxer (không re-encode).

### 3.6 Trả kết quả
- Xuất file `VJTS_<plate>_<timestamp>.mp4` + (tùy chọn) JSON log segments.  
- UI/CLI/REST trả đường dẫn tải về.

---

## 4. Thiết kế Dữ liệu (Metadata Database – tùy chọn nhưng khuyến khích)
### 4.1 Lược đồ (SQLite)
**Table `cameras`**
- `camera_id` TEXT PK  
- `name` TEXT, `location` TEXT, `timezone` TEXT

**Table `videos`**
- `video_id` INTEGER PK AUTOINCREMENT  
- `camera_id` TEXT FK → cameras.camera_id  
- `path` TEXT UNIQUE NOT NULL  
- `start_ts` DATETIME, `end_ts` DATETIME, `fps` REAL, `resolution` TEXT

**Table `appearances`**
- `appearance_id` INTEGER PK AUTOINCREMENT  
- `plate` TEXT NOT NULL  
- `camera_id` TEXT  
- `video_id` INTEGER FK → videos.video_id  
- `start_time` REAL NOT NULL  
- `end_time` REAL NOT NULL  
- `score_lp` REAL, `score_ocr` REAL, `match_mode` TEXT

**Table `jobs`** (theo dõi yêu cầu truy vết)
- `job_id` TEXT PK (UUID)  
- `plate` TEXT NOT NULL  
- `status` TEXT CHECK IN ('queued','running','done','failed')  
- `created_at` DATETIME, `finished_at` DATETIME  
- `result_video` TEXT, `segments_json` TEXT

### 4.2 Chỉ mục (Indexes)
- `idx_appearances_plate` on (`plate`).  
- `idx_videos_camera_ts` on (`camera_id`,`start_ts`).

---

## 5. API & Giao diện (khuyến khích)
### 5.1 REST API (FastAPI)
- `POST /jobs` – body `{ plate: string }` → tạo job, trả `job_id`.
- `GET /jobs/{id}` – trạng thái, danh sách segments, link video kết quả.
- `POST /upload` – upload video mới (gắn `camera_id`, `start_ts`).
- `GET /videos` – liệt kê video đã nạp.
- `GET /health` – kiểm tra sống.

### 5.2 UI Web (tối giản)
- Form nhập biển số + nút chạy.  
- Bảng hiển thị tiến trình (status), log, danh sách segment (camera, start, end).  
- Video player phát kết quả.

---

## 6. Cấu trúc thư mục dự án
```
VJTS/
├─ README.md
├─ requirements.txt / environment.yml
├─ config/
│   ├─ config.yaml
│   └─ camera_registry.csv
├─ data/
│   ├─ videos/             # đầu vào
│   └─ outputs/            # kết quả + logs
├─ db/
│   └─ vjts.sqlite
├─ src/
│   ├─ app.py              # FastAPI/Flask
│   ├─ cli.py              # chạy CLI: python -m src.cli --plate "51G-123.45"
│   ├─ detector.py         # YOLO wrapper
│   ├─ ocr.py              # EasyOCR/PaddleOCR wrapper
│   ├─ tracker.py          # IOU/SORT/DeepSORT/ByteTrack
│   ├─ matcher.py          # khớp chuỗi OCR ↔ plate
│   ├─ segmenter.py        # tạo & quản lý segments
│   ├─ videoio.py          # đọc/ghi video, ffmpeg utils
│   ├─ concat.py           # ghép clip
│   ├─ db.py               # SQLite + SQLAlchemy models
│   └─ utils.py            # chuẩn hóa, logging, time
├─ models/
│   └─ lp_yolov8.onnx      # ví dụ mô hình detector biển số
├─ docker/
│   ├─ Dockerfile
│   └─ docker-compose.yml (tùy chọn)
└─ tests/
    ├─ test_matcher.py
    ├─ test_segmenter.py
    └─ test_videoio.py
```

---

## 7. Cấu hình mẫu (`config/config.yaml`)
```yaml
video_dir: "data/videos"
output_dir: "data/outputs"
model:
  detector: "models/lp_yolov8.onnx"
  conf_threshold: 0.35
  nms_threshold: 0.5
ocr:
  engine: "easyocr"  # or paddle
  langs: ["en"]
matching:
  mode: "relaxed"
  max_distance: 2     # Levenshtein
tracking:
  method: "iou"       # or sort|deepsort|bytetrack
  lost_tolerance: 10  # frames
trim:
  pre_pad: 0.5        # giây
  post_pad: 0.5
concat:
  method: "moviepy"   # or ffmpeg
ffmpeg:
  binary: "ffmpeg"
```

---

## 8. Thuật toán & Pseudocode
### 8.1 Khớp biển số (chuẩn hóa + Levenshtein)
```
function normalize(s):
  s = upper(remove_spaces(dash_dot_to_empty(s)))
  s = s.replace('O','0').replace('I','1')
  return s

function is_match(plate_target, ocr_text, mode, max_distance):
  a = normalize(plate_target)
  b = normalize(ocr_text)
  if mode == 'exact': return a == b
  return levenshtein(a,b) <= max_distance
```

### 8.2 Pipeline duyệt video
```
for video in video_list:
  fps, duration = open_video(video)
  in_segment = false
  last_seen_frame = -1
  for frame_idx, frame in iterate_frames(video, step=1 or adaptive):
    boxes = detect_lp(frame)
    matches = []
    for box in boxes:
      roi = crop(frame, box)
      text = ocr(roi)
      if is_match(target_plate, text, mode, max_dist):
        matches.append(box)
    if matches not empty:
      track(matches)  # hoặc iou match đơn giản
      if not in_segment:
        in_segment = true
        start_time = frame_idx / fps
      last_seen_frame = frame_idx
    else:
      if in_segment and (frame_idx - last_seen_frame) > lost_tolerance:
        end_time = last_seen_frame / fps
        save_segment(video, start_time, end_time)
        in_segment = false
  if in_segment:
    end_time = last_seen_frame / fps
    save_segment(video, start_time, end_time)
```

### 8.3 Cắt & ghép
```
segments = load_segments()
segments = sort_by_absolute_time(segments)
clips = []
for seg in segments:
  clip = subclip(seg.video, seg.start - pre_pad, seg.end + post_pad)
  clips.append(clip)
result = concatenate(clips)
save(result, output_path)
```

---

## 9. Thiết lập môi trường & chạy
### 9.1 `requirements.txt`
```
ultralytics==8.*
opencv-python
numpy
moviepy
pillow
easyocr
python-Levenshtein
fastapi
uvicorn
sqlalchemy
pydantic
python-dotenv
```

### 9.2 Lệnh nhanh (CLI)
```
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
python -m src.cli --plate "51G-123.45" --config config/config.yaml
# Kết quả: data/outputs/VJTS_51G12345_YYYYmmdd-HHMMSS.mp4
```

### 9.3 Docker (tùy chọn)
**Dockerfile (gợi ý tối giản)**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python","-m","src.cli","--plate","51G-123.45","--config","config/config.yaml"]
```

**Chạy**
```
docker build -t vjts .
docker run --rm -v $(pwd)/data:/app/data vjts
```

---

## 10. Kiểm thử & Đánh giá
### 10.1 Bộ test tối thiểu
- **Unit**: `test_matcher.py` (normalize & Levenshtein), `test_segmenter.py`, `test_videoio.py`.
- **Integration**: chạy pipeline trên 3–5 video mẫu có gán nhãn ground-truth.

### 10.2 Chỉ số đánh giá
- **Detector/OCR**: Precision, Recall ở mức bbox/chuỗi.
- **Tracking**: tỷ lệ mất bám, số ID switch.
- **Segment**: Lỗi thời điểm cắt (MAE, ± giây), tỷ lệ over/under-trim.
- **E2E**: % lần xuất hiện được trích xuất đúng, tổng thời gian xử lý/video.

### 10.3 Kịch bản kiểm thử
- Biển số rõ nét, ban ngày (dễ).  
- Trời tối/mưa/ánh sáng ngược (khó).  
- Nhiều xe chen nhau, biển số bị che cục bộ.  
- Camera rung/lệch góc.

---

## 11. Rủi ro & Giảm thiểu
- **OCR lỗi ký tự (O↔0, I↔1)** → dùng chuẩn hóa + relaxed match + kiểm tra định dạng VN.  
- **Biển số mờ/che** → tăng độ phân giải ROI, sharpen, hoặc dùng super-resolution.  
- **Nhiều biển số trong khung** → ưu tiên theo vị trí/diện tích lớn, kết hợp tracking ổn định.  
- **Sai timestamp/liên camera** → ép quy ước tên file `CAMID_YYYYmmdd_HHMMSS.mp4`, validate khi nạp.

---

## 12. Lộ trình thực hiện (đề xuất cho đồ án ~2–4 tuần)
**Tuần 1**: Khung dự án, đọc video, detector + OCR thử nghiệm, matcher & log segment.  
**Tuần 2**: Hoàn thiện segmenter + trim + concat, xuất video.  
**Tuần 3**: Thêm UI/CLI tử tế, (tùy chọn) SQLite, viết test & đánh giá.  
**Tuần 4**: Tối ưu, viết báo cáo, quay demo.

---

## 13. Hướng dẫn gắn nhãn & Dữ liệu (nếu cần fine-tune)
- Gắn nhãn bbox **biển số** (không phải cả xe) theo định dạng YOLO.  
- Chuẩn hóa kích thước ảnh/khung hình khi train.  
- Tạo **synthetic augmentations** (blur, noise, low-light) để tăng robust.

---

## 14. Quyền riêng tư & Pháp lý (Awareness)
- Dữ liệu video có thể chứa **thông tin cá nhân**; dùng **ẩn danh** khi công bố.  
- Chỉ sử dụng dữ liệu cho mục đích **học thuật/đồ án**, không triển khai thương mại khi chưa có phép.  
- Tuân thủ quy định địa phương về **giám sát hình ảnh**.

---

## 15. Phụ lục
### 15.1 CLI tham số gợi ý
```
python -m src.cli \
  --plate "51G-123.45" \
  --video-dir data/videos \
  --output-dir data/outputs \
  --detector models/lp_yolov8.onnx \
  --conf 0.35 --nms 0.5 \
  --ocr-engine easyocr --ocr-langs en \
  --match relaxed --max-dist 2 \
  --track iou --lost 10 \
  --pre-pad 0.5 --post-pad 0.5 \
  --concat moviepy
```

### 15.2 Mẫu JSON kết quả segments
```json
{
  "plate": "51G-123.45",
  "segments": [
    {
      "camera_id": "CAM01",
      "video_path": "data/videos/CAM01_2025-09-01_080000.mp4",
      "start_time": 12.48,
      "end_time": 19.92,
      "score_lp": 0.92,
      "score_ocr": 0.88
    }
  ],
  "result_video": "data/outputs/VJTS_51G12345_2025-10-02-213000.mp4"
}
```

### 15.3 Gợi ý tối ưu hiệu năng
- Bỏ qua khung (frame skipping) *khi ít biến động*, giảm tần suất OCR.  
- Dùng batch inference với YOLO (tăng throughput).  
- Chạy OCR chỉ trên **ROI đã ổn định** từ tracking.

---

**Kết luận:** Tài liệu này đủ để khởi động, triển khai MVP và mở rộng dần. Bạn có thể copy sang Cursor làm **README.md** cho repo đồ án.

