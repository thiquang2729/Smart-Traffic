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
const stopJobBtn = document.getElementById('stopJob');
const trajectorySection = document.getElementById('trajectorySection');
const trajectoryInfo = document.getElementById('trajectoryInfo');

let uploadedUrls = [], currentIndex = 0, segments = [], currentResultUrl = null;
let allCrops = [], visibleCrops = 4;
let currentJobId = null;
let currentEventSource = null;

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

// === Stop Job Button ===
stopJobBtn.onclick = async () => {
    if (!currentJobId) {
        showLogStatus('⚠️ Không có job đang chạy', 'error');
        return;
    }
    
    try {
        const formData = new FormData();
        formData.append('job_id', currentJobId);
        
        const resp = await fetch('/cancel', {
            method: 'POST',
            body: formData
        });
        
        const data = await resp.json();
        if (data.status === 'cancelled') {
            showLogStatus('⏹️ Đã gửi yêu cầu dừng xử lý...', 'info');
            stopJobBtn.style.display = 'none';
            runAllBtn.disabled = false;
            
            // Close EventSource
            if (currentEventSource) {
                currentEventSource.close();
                currentEventSource = null;
            }
        } else {
            showLogStatus('⚠️ ' + data.message, 'error');
        }
    } catch (err) {
        showLogStatus('❌ Lỗi khi dừng: ' + err.message, 'error');
    }
};

// === Run Button unified ===
runAllBtn.onclick = async () => {
    // Reset state
    currentJobId = null;
    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }
    
    showLogStatus('🚀 Đang chạy xử lý video...', 'info');
    linksEl.innerHTML = '';
    cropsEl.innerHTML = '';
    allCrops = [];
    visibleCrops = 4;
    segments = [];
    trajectorySection.style.display = 'none';
    updateCropsDisplay();
    
    // Show stop button, disable run button
    stopJobBtn.style.display = 'block';
    runAllBtn.disabled = true;
    
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
        stopJobBtn.style.display = 'none';
        runAllBtn.disabled = false;
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
    currentEventSource = es;
    
    // Handle job_id event
    es.addEventListener('job_id', (evt) => {
        try {
            const data = JSON.parse(evt.data);
            currentJobId = data.job_id;
            console.log('Job ID:', currentJobId);
        } catch (e) {
            console.error('Error parsing job_id:', e);
        }
    });
    
    es.onmessage = (e) => {
        try {
            const d = JSON.parse(e.data);
            if (d.type === 'status') showLogStatus('🔄 ' + d.stage);
            else if (d.type === 'video_start') showLogStatus('🎬 ' + d.path.split('/').pop());
            else if (d.type === 'progress') {
                if (d.message) {
                    showLogStatus(d.message);
                } else {
                    showLogStatus(`⏳ Frame ${d.frame}${d.matched ? ' - Tìm thấy biển số!' : ''}`);
                }
            }
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
    
    es.addEventListener('cancelled', (evt) => {
        let msg = {};
        try {
            msg = JSON.parse(evt.data);
        } catch { }
        showLogStatus('⏹️ Đã dừng xử lý: ' + (msg.message || 'Job đã bị hủy'), 'error');
        stopJobBtn.style.display = 'none';
        runAllBtn.disabled = false;
        currentJobId = null;
        es.close();
        currentEventSource = null;
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
            
            // Hiển thị trajectory data nếu có
            if (msg.segments && msg.segments.length > 0) {
                segments = msg.segments;
                displayTrajectoryInfo(msg.segments);
            }
        } else if (msg.error) {
            if (msg.error === 'cancelled') {
                showLogStatus('⏹️ Đã dừng xử lý', 'error');
            } else {
                showLogStatus('❌ Job thất bại: ' + (msg.message || msg.error), 'error');
            }
            downloadSection.style.display = 'none';
            trajectorySection.style.display = 'none';
        }
        stopJobBtn.style.display = 'none';
        runAllBtn.disabled = false;
        currentJobId = null;
        es.close();
        currentEventSource = null;
    });
    
    es.onerror = (err) => {
        console.error('EventSource error:', err);
        showLogStatus('❌ Lỗi kết nối', 'error');
        stopJobBtn.style.display = 'none';
        runAllBtn.disabled = false;
        currentJobId = null;
        currentEventSource = null;
    };
};

// === Display Trajectory Info ===
function displayTrajectoryInfo(segments) {
    if (!segments || segments.length === 0) {
        trajectorySection.style.display = 'none';
        return;
    }
    
    // Lọc các segments có trajectory data
    const segmentsWithTrajectory = segments.filter(s => s.trajectory && Object.keys(s.trajectory).length > 0);
    
    if (segmentsWithTrajectory.length === 0) {
        trajectorySection.style.display = 'none';
        return;
    }
    
    trajectorySection.style.display = 'block';
    trajectoryInfo.innerHTML = '';
    
    // Thêm note về giá trị ước lượng nếu có segment không có calibration
    const hasEstimated = segmentsWithTrajectory.some(s => !s.trajectory.speed_kmh);
    if (hasEstimated) {
        const noteDiv = document.createElement('div');
        noteDiv.style.cssText = 'font-size:11px;color:#aab2c8;margin-bottom:8px;font-style:italic;';
        noteDiv.textContent = '* Giá trị ước lượng (1px ≈ 0.01m). Để có giá trị chính xác, hãy set calibration trong config.';
        trajectoryInfo.appendChild(noteDiv);
    }
    
    segmentsWithTrajectory.forEach((segment, idx) => {
        const traj = segment.trajectory;
        const segmentDiv = document.createElement('div');
        segmentDiv.className = 'trajectory-segment';
        
        // Format thời gian
        const startTime = formatTime(segment.start_time);
        const endTime = formatTime(segment.end_time);
        const duration = (segment.end_time - segment.start_time).toFixed(1);
        
        segmentDiv.innerHTML = `
            <div class="trajectory-segment-header">
                📍 Đoạn ${idx + 1}: ${startTime} - ${endTime} (${duration}s)
            </div>
            <div class="trajectory-metrics">
                ${traj.speed_px_per_sec !== undefined ? `
                <div class="trajectory-metric">
                    <div class="trajectory-metric-label">Tốc độ</div>
                    <div class="trajectory-metric-value">
                        ${traj.speed_px_per_sec.toFixed(1)} px/s
                        ${traj.speed_kmh !== undefined && traj.speed_kmh !== null ? 
                            `<span class="highlight" style="margin-left:8px;">(${traj.speed_kmh.toFixed(1)} km/h)</span>` : 
                            (() => {
                                // Ước lượng km/h dựa trên giả định: 1 pixel ≈ 0.01m (có thể điều chỉnh)
                                // Đây là giá trị ước lượng, không chính xác như calibration thực tế
                                const estimated_pixel_to_meter = 0.01; // Giả định mặc định
                                const estimated_kmh = (traj.speed_px_per_sec * estimated_pixel_to_meter * 3.6).toFixed(1);
                                return `<span style="margin-left:8px;color:#aab2c8;font-size:11px;">(≈${estimated_kmh} km/h*)</span>`;
                            })()}
                    </div>
                </div>
                ` : ''}
                ${traj.direction_deg !== undefined ? `
                <div class="trajectory-metric">
                    <div class="trajectory-metric-label">Hướng</div>
                    <div class="trajectory-metric-value">${traj.direction_name || 'N/A'} (${traj.direction_deg.toFixed(1)}°)</div>
                </div>
                ` : ''}
                ${traj.total_distance_px !== undefined ? `
                <div class="trajectory-metric">
                    <div class="trajectory-metric-label">Quãng đường</div>
                    <div class="trajectory-metric-value">${traj.total_distance_px.toFixed(0)} px${traj.total_distance_m ? ` (${traj.total_distance_m.toFixed(1)}m)` : ''}</div>
                </div>
                ` : ''}
                ${traj.max_speed_px_per_sec !== undefined ? `
                <div class="trajectory-metric">
                    <div class="trajectory-metric-label">Tốc độ max</div>
                    <div class="trajectory-metric-value">
                        ${traj.max_speed_px_per_sec.toFixed(1)} px/s
                        ${traj.max_speed_kmh !== undefined && traj.max_speed_kmh !== null ? 
                            `<span class="highlight" style="margin-left:8px;">(${traj.max_speed_kmh.toFixed(1)} km/h)</span>` : 
                            (() => {
                                // Ước lượng km/h cho max speed
                                const estimated_pixel_to_meter = 0.01;
                                const estimated_kmh = (traj.max_speed_px_per_sec * estimated_pixel_to_meter * 3.6).toFixed(1);
                                return `<span style="margin-left:8px;color:#aab2c8;font-size:11px;">(≈${estimated_kmh} km/h*)</span>`;
                            })()}
                    </div>
                </div>
                ` : ''}
            </div>
        `;
        
        trajectoryInfo.appendChild(segmentDiv);
    });
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60);
    const secsInt = Math.floor(secs);
    const secsDec = Math.floor((secs - secsInt) * 10);
    return `${mins}:${String(secsInt).padStart(2, '0')}.${secsDec}`;
}