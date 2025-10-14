// === DOM elements ===
const filesEl = document.getElementById('files');
const selectVideosBtn = document.getElementById('selectVideos');
const runAllBtn = document.getElementById('runAll');
const logStatus = document.getElementById('logStatus');
const logMessage = document.getElementById('logMessage');
const logEl = document.getElementById('log');
const downloadSection = document.getElementById('downloadSection');
const downloadResultBtn = document.getElementById('downloadResult');
const playResultBtn = document.getElementById('playResult');
const linksEl = document.getElementById('links');
const cropsEl = document.getElementById('crops');
const showMoreBtn = document.getElementById('showMoreCrops');
const videoOriginal = document.getElementById('videoOriginal');
const videoResult = document.getElementById('videoResult');
const videoTop = document.getElementById('videoTop');
const scrubber = document.getElementById('scrubber');
const playPauseBtn = document.getElementById('playPause');
const timeLabel = document.getElementById('timeLabel');
const zoomModal = document.getElementById('zoomModal');
const zoomImage = document.getElementById('zoomImage');
const zoomClose = document.querySelector('.zoom-close');

let uploadedUrls = [], currentIndex = 0, segments = [], currentResultUrl = null;
let allCrops = [], visibleCrops = 4;

// === UI helpers ===
function showLogStatus(msg, type = 'info') {
    logStatus.style.display = 'flex';
    logMessage.textContent = msg;
    logStatus.className = `log-status ${type}`;
    logEl.style.display = 'none';
    const spinner = logStatus.querySelector('.loading-spinner');
    spinner.style.display = (type === 'info') ? 'inline-block' : 'none';
}
function showLogContent(c) {
    logEl.textContent = c;
    logEl.style.display = 'block';
    logStatus.style.display = 'none';
}

// === Zoom logic ===
function openZoom(src) {
    zoomImage.src = src;
    zoomModal.style.display = 'flex';
}
zoomClose.onclick = () => zoomModal.style.display = 'none';
zoomModal.onclick = e => {
    if (e.target === zoomModal) zoomModal.style.display = 'none';
};

// === Select local videos ===
selectVideosBtn.onclick = () => filesEl.click();
filesEl.onchange = () => {
    uploadedUrls.forEach(u => URL.revokeObjectURL(u));
    uploadedUrls = Array.from(filesEl.files || []).map(f => URL.createObjectURL(f));
    if (uploadedUrls.length > 0) {
        videoTop.src = uploadedUrls[0];
        videoOriginal.src = uploadedUrls[0];
    }
};

// === Zoom on click frame ===
[videoTop, videoOriginal, videoResult].forEach(v => {
    v.onclick = () => {
        const c = document.createElement('canvas');
        const ctx = c.getContext('2d');
        c.width = v.videoWidth || 640;
        c.height = v.videoHeight || 360;
        ctx.drawImage(v, 0, 0, c.width, c.height);
        openZoom(c.toDataURL('image/jpeg'));
    };
});

// === Show crops preview ===
function updateCropsDisplay() {
    cropsEl.innerHTML = '';
    const toShow = allCrops.slice(0, visibleCrops);
    toShow.forEach(url => {
        const img = document.createElement('img');
        img.src = url;
        img.onclick = () => openZoom(url);
        cropsEl.appendChild(img);
    });
    if (allCrops.length > visibleCrops) {
        showMoreBtn.style.display = 'block';
        showMoreBtn.textContent = `Xem thêm (${allCrops.length - visibleCrops})`;
    } else {
        showMoreBtn.style.display = 'none';
    }
}
showMoreBtn.onclick = () => {
    visibleCrops = Math.min(visibleCrops + 4, allCrops.length);
    updateCropsDisplay();
};

// === Download & Play result ===
downloadResultBtn.onclick = () => {
    if (currentResultUrl) {
        const a = document.createElement('a');
        a.href = currentResultUrl;
        a.download = 'video_result.mp4';
        a.click();
    }
};
playResultBtn.onclick = () => {
    if (currentResultUrl) {
        videoResult.src = currentResultUrl;
        videoResult.play();
    }
};

// === Run Button unified ===
runAllBtn.onclick = async () => {
    showLogStatus('🚀 Đang chạy xử lý video...', 'info');
    linksEl.innerHTML = '';
    cropsEl.innerHTML = '';
    allCrops = [];
    visibleCrops = 4;
    updateCropsDisplay();
    try {
        const fdUp = new FormData();
        const files = filesEl.files;
        if (files.length > 0) {
            for (let i = 0; i < files.length; i++) fdUp.append('files', files[i]);
            showLogStatus(`📤 Đang tải lên ${files.length} file...`, 'info');
            const respUp = await fetch('/upload', {
                method: 'POST',
                body: fdUp
            });
            const dataUp = await respUp.json();
            if (!dataUp.upload_dir) throw new Error('Upload thất bại');
            showLogStatus('✅ Upload thành công, bắt đầu xử lý...', 'info');
            sseRun(dataUp.upload_dir);
        } else {
            showLogStatus('▶️ Không có file upload — chạy thư mục có sẵn', 'info');
            sseRun();
        }
    } catch (err) {
        showLogStatus('❌ Lỗi: ' + err.message, 'error');
    }
};

// === SSE realtime run ===
const sseRun = (dirOverride = null) => {
    const params = new URLSearchParams({
        plate: document.getElementById('plate').value,
        video_dir: dirOverride || document.getElementById('video_dir').value,
        output_dir: document.getElementById('output_dir').value
    });
    const es = new EventSource(`/events?${params.toString()}`);
    es.onmessage = (e) => {
        try {
            const d = JSON.parse(e.data);
            if (d.type === 'status') showLogStatus('🔄 ' + d.stage);
            else if (d.type === 'video_start') showLogStatus('🎬 ' + d.path.split('/').pop());
            else if (d.type === 'progress') showLogStatus(`⏳ Frame ${d.frame}${d.matched ? ' - Tìm thấy biển số!' : ''}`);
            else if (d.type === 'video_done') showLogStatus('✅ Xong video (' + d.segments + ' đoạn)', 'success');
            else if (d.type === 'concat_done') showLogStatus('🎯 Đang tạo video kết quả...');
            else showLogContent(JSON.stringify(d, null, 2));
        } catch {
            showLogContent(e.data);
        }
    };
    es.addEventListener('crop', (evt) => {
        allCrops.unshift(evt.data);
        updateCropsDisplay();
    });
    es.addEventListener('result', (evt) => {
        let msg = {};
        try {
            msg = JSON.parse(evt.data);
        } catch { }
        if (msg.result_video) {
            showLogStatus('🎉 Hoàn thành! Video kết quả sẵn sàng', 'success');
            const url = `/download/result?path=${encodeURIComponent(msg.result_video)}`;
            currentResultUrl = url;
            downloadSection.style.display = 'block';
            linksEl.innerHTML = `<a href="${url}" target="_blank">Tải video kết quả</a>`;
            videoResult.src = url;
        } else if (msg.error) {
            showLogStatus('❌ Job thất bại: ' + (msg.message || msg.error), 'error');
            downloadSection.style.display = 'none';
        }
        es.close();
    });
};