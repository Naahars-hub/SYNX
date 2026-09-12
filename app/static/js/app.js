// SYNX Legal Metrology Compliance Checker - Client Logic

let currentFiles = [];
let currentMobileImages = [];
let currentSampleNames = [];
let currentAudit = null;
let loadedImage = null;
let ocrBoxes = [];
let activeAngleId = 1;
let isClaheView = false;
let activePreviewType = 'file';

// Authentication State
let currentUser = null;
let authToken = localStorage.getItem('synx_auth_token') || null;
let googleAuthConfig = null;

// DOM Elements
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const sampleGrid = document.getElementById('sampleGrid');
const labelCanvas = document.getElementById('labelCanvas');
const ctx = labelCanvas.getContext('2d');
const loadingOverlay = document.getElementById('loadingOverlay');
const canvasTooltip = document.getElementById('canvasTooltip');
const btnDownloadPdf = document.getElementById('btnDownloadPdf');

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initAuth();
  if (document.getElementById('sampleGrid')) {
    loadBenchmarkSamples();
  }
  setupDropZone();
  setupCanvasInteraction();
});

// Theme Management (Fresh Light & Obsidian Slate)
function initTheme() {
  const savedTheme = localStorage.getItem('synx_theme') || 'light';
  applyTheme(savedTheme);
}

function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
  const newTheme = (currentTheme === 'dark') ? 'light' : 'dark';
  applyTheme(newTheme);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('synx_theme', theme);

  const sunIcon = document.getElementById('themeIconSun');
  const moonIcon = document.getElementById('themeIconMoon');
  const textEl = document.getElementById('themeText');

  if (theme === 'dark') {
    if (sunIcon) sunIcon.style.display = 'none';
    if (moonIcon) moonIcon.style.display = 'inline-block';
    if (textEl) textEl.textContent = 'Dark';
  } else {
    if (sunIcon) sunIcon.style.display = 'inline-block';
    if (moonIcon) moonIcon.style.display = 'none';
    if (textEl) textEl.textContent = 'Light';
  }
}

// Load Benchmark Samples
async function loadBenchmarkSamples() {
  const grid = document.getElementById('sampleGrid');
  if (!grid) return;
  try {
    const res = await fetch('/api/samples');
    const samples = await res.json();
    grid.innerHTML = '';

    samples.forEach((s, idx) => {
      const btn = document.createElement('div');
      btn.className = 'benchmark-btn';
      btn.id = `sample-btn-${idx}`;
      btn.innerHTML = `
        <b>${s.title.split(':')[0]}</b>
        <div style="font-size: 0.65rem; color: #9ca3af;">${s.description.substring(0, 45)}...</div>
      `;
      btn.onclick = () => selectSample(s, btn);
      grid.appendChild(btn);
    });

    // Auto-select first sample for instant demo
    if (samples.length > 0) {
      selectSample(samples[0], document.getElementById('sample-btn-0'));
    }
  } catch (err) {
    console.error('Failed to load samples:', err);
    if (grid) grid.innerHTML = '<div style="color: #ef4444; font-size: 0.75rem;">Failed to load benchmark samples.</div>';
  }
}

// Select a sample
function selectSample(sample, btnElement) {
  document.querySelectorAll('.benchmark-btn').forEach(b => b.classList.remove('active'));
  if (btnElement) btnElement.classList.add('active');

  currentSampleNames = [sample.filename];
  currentFiles = [];
  currentMobileImages = [];
  renderUploadPreviews();
  document.getElementById('angleTabsContainer').style.display = 'none';
  const btnClahe = document.getElementById('btnToggleClahe');
  if (btnClahe) {
    btnClahe.style.display = 'none';
    btnClahe.classList.remove('active');
  }
  isClaheView = false;

  // Render image preview on canvas
  loadImageOntoCanvas(sample.image_url);
}

// Setup Drag & Drop
function setupDropZone() {
  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
    }, false);
  });

  dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
      handleFiles(files);
    }
  });
}

const MAX_UPLOAD_FILES = 6;
const MAX_FILE_SIZE_MB = 10;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp', 'bmp', 'tiff', 'pdf'];
let activePreviewIndex = 0;

function handleFileSelect(event) {
  if (event.target.files.length > 0) {
    handleFiles(event.target.files);
  }
}

function handleFiles(files) {
  const incoming = Array.from(files);
  if (incoming.length === 0) return;

  // Merge new files with existing without duplicate name & size
  let combined = [...currentFiles];
  for (const f of incoming) {
    if (!combined.some(existing => existing.name === f.name && existing.size === f.size)) {
      combined.push(f);
    }
  }

  // 1. Check max file count limit
  if (combined.length > MAX_UPLOAD_FILES) {
    alert(`Upload Limit Exceeded:\nYou can upload a maximum of ${MAX_UPLOAD_FILES} images/documents per audit.\n\nTotal items: ${combined.length}. Keeping the first ${MAX_UPLOAD_FILES} files.`);
    combined = combined.slice(0, MAX_UPLOAD_FILES);
  }

  // 2. Validate each file size and format
  const validFiles = [];
  for (const file of combined) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      alert(`Unsupported Format: "${file.name}"\n\nPlease upload standard packaging label images or documents (JPG, PNG, WEBP, BMP, PDF).`);
      continue;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
      alert(`File Too Large: "${file.name}" (${sizeMB} MB)\n\nThe maximum allowed file size is ${MAX_FILE_SIZE_MB} MB per file.`);
      continue;
    }

    if (file.size === 0) {
      alert(`Empty File: "${file.name}" is 0 bytes. Skipping.`);
      continue;
    }

    validFiles.push(file);
  }

  currentFiles = validFiles;
  currentMobileImages = [];
  currentSampleNames = [];
  document.querySelectorAll('.benchmark-btn').forEach(b => b.classList.remove('active'));

  renderUploadPreviews();

  if (currentFiles.length > 0) {
    previewFileOnCanvas(currentFiles.length - 1);
  } else {
    resetCanvas();
  }
}

function renderUploadPreviews() {
  const container = document.getElementById('uploadPreviewContainer');
  const grid = document.getElementById('uploadPreviewGrid');
  const badge = document.getElementById('uploadCountBadge');
  if (!container || !grid) return;

  const totalCount = currentFiles.length + currentMobileImages.length;
  if (totalCount === 0) {
    container.style.display = 'none';
    grid.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  if (badge) badge.textContent = `${totalCount} / ${MAX_UPLOAD_FILES}`;
  grid.innerHTML = '';

  // 1. Render Local Files
  currentFiles.forEach((file, idx) => {
    const isPdf = file.name.toLowerCase().endsWith('.pdf');
    const sizeStr = file.size > 1024 * 1024 
      ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
      : `${(file.size / 1024).toFixed(0)} KB`;

    const card = document.createElement('div');
    const isActive = (activePreviewType === 'file' && idx === activePreviewIndex);
    card.className = `upload-file-card ${isActive ? 'active-preview' : ''}`;
    card.id = `upload-card-${idx}`;
    card.title = `Click to preview Angle ${idx + 1} (${file.name})`;
    card.onclick = (e) => {
      if (e.target.closest('.upload-file-remove')) return;
      previewFileOnCanvas(idx);
    };

    let thumbHtml = '';
    if (isPdf) {
      thumbHtml = `<div class="upload-file-doc-icon">PDF</div>`;
    } else {
      const objUrl = URL.createObjectURL(file);
      thumbHtml = `<img src="${objUrl}" class="upload-file-thumb" alt="Angle ${idx + 1}">`;
    }

    card.innerHTML = `
      ${thumbHtml}
      <div class="upload-file-info">
        <div class="upload-file-name">${escapeHtml(file.name)}</div>
        <div class="upload-file-meta">
          <span class="upload-angle-pill">Angle ${idx + 1}</span>
          <span>${sizeStr}</span>
        </div>
      </div>
      <button type="button" class="upload-file-remove" title="Remove this file" onclick="removeUploadedFile(${idx}, event)">
        &times;
      </button>
    `;
    grid.appendChild(card);
  });

  // 2. Render Mobile Phone Uploads
  currentMobileImages.forEach((img, mIdx) => {
    const angleNum = currentFiles.length + mIdx + 1;
    const card = document.createElement('div');
    const isActive = (activePreviewType === 'mobile' && mIdx === activePreviewIndex) || (currentFiles.length === 0 && mIdx === activePreviewIndex);
    card.className = `upload-file-card ${isActive ? 'active-preview' : ''}`;
    card.id = `mobile-card-${mIdx}`;
    card.title = `Click to preview Angle ${angleNum} (Mobile Capture)`;
    card.onclick = (e) => {
      if (e.target.closest('.upload-file-remove')) return;
      previewMobileImageOnCanvas(mIdx);
    };

    const cleanName = img.filename.replace(/^mobile_\d+_[a-f0-9]+_/, '');

    card.innerHTML = `
      <img src="${img.image_url}" class="upload-file-thumb" alt="Angle ${angleNum}">
      <div class="upload-file-info">
        <div class="upload-file-name" title="${escapeHtml(img.filename)}">${escapeHtml(cleanName || img.filename)}</div>
        <div class="upload-file-meta">
          <span class="upload-angle-pill" style="background: rgba(16, 185, 129, 0.12); color: #059669; border: 1px solid rgba(16, 185, 129, 0.3);">Angle ${angleNum}</span>
          <span>📱 Mobile Capture</span>
        </div>
      </div>
      <button type="button" class="upload-file-remove" title="Remove this snapped angle" onclick="removeMobileUploadedFile(${mIdx}, event)">
        &times;
      </button>
    `;
    grid.appendChild(card);
  });
}

function previewFileOnCanvas(idx) {
  if (idx < 0 || idx >= currentFiles.length) return;
  activePreviewIndex = idx;
  activePreviewType = 'file';
  const file = currentFiles[idx];
  const isPdf = file.name.toLowerCase().endsWith('.pdf');

  document.querySelectorAll('.upload-file-card').forEach(c => c.classList.remove('active-preview'));
  const card = document.getElementById(`upload-card-${idx}`);
  if (card) card.classList.add('active-preview');

  if (isPdf) {
    renderPdfPlaceholder(file, idx + 1);
    document.getElementById('canvasStats').textContent = `Angle ${idx + 1}: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB PDF)`;
  } else {
    const reader = new FileReader();
    reader.onload = (e) => {
      loadImageOntoCanvas(e.target.result);
    };
    reader.readAsDataURL(file);
    const totalCount = currentFiles.length + currentMobileImages.length;
    document.getElementById('canvasStats').textContent = `Angle ${idx + 1} of ${totalCount}: ${file.name}`;
  }

  const tabs = document.getElementById('angleTabsContainer');
  if (tabs) tabs.style.display = 'none';
}

function previewMobileImageOnCanvas(mIdx) {
  if (mIdx < 0 || mIdx >= currentMobileImages.length) return;
  activePreviewIndex = mIdx;
  activePreviewType = 'mobile';
  const imgData = currentMobileImages[mIdx];

  document.querySelectorAll('.upload-file-card').forEach(c => c.classList.remove('active-preview'));
  const card = document.getElementById(`mobile-card-${mIdx}`);
  if (card) card.classList.add('active-preview');

  loadImageOntoCanvas(imgData.image_url);
  const totalCount = currentFiles.length + currentMobileImages.length;
  const angleNum = currentFiles.length + mIdx + 1;
  const cleanName = imgData.filename.replace(/^mobile_\d+_[a-f0-9]+_/, '');
  const statsEl = document.getElementById('canvasStats');
  if (statsEl) {
    statsEl.textContent = `Angle ${angleNum} of ${totalCount} (Mobile): ${cleanName || imgData.filename}`;
  }

  const tabs = document.getElementById('angleTabsContainer');
  if (tabs) tabs.style.display = 'none';
}

function removeUploadedFile(idx, event) {
  if (event) event.stopPropagation();
  if (idx < 0 || idx >= currentFiles.length) return;
  currentFiles.splice(idx, 1);
  renderUploadPreviews();
  if (currentFiles.length > 0) {
    const nextIdx = Math.min(activePreviewIndex, currentFiles.length - 1);
    previewFileOnCanvas(nextIdx);
  } else if (currentMobileImages.length > 0) {
    previewMobileImageOnCanvas(0);
  } else {
    resetCanvas();
    const fileInputEl = document.getElementById('fileInput');
    if (fileInputEl) fileInputEl.value = '';
  }
}

async function removeMobileUploadedFile(idx, event) {
  if (event) event.stopPropagation();
  if (idx < 0 || idx >= currentMobileImages.length) return;

  const target = currentMobileImages[idx];
  const targetSession = currentMobileSession;

  // Optimistically remove from state for instant UI responsiveness
  currentMobileImages.splice(idx, 1);
  currentSampleNames = currentMobileImages.map(m => m.filename);

  renderUploadPreviews();
  updateModalReceivedThumbs();

  if (currentMobileImages.length > 0) {
    const nextIdx = Math.min(idx, currentMobileImages.length - 1);
    previewMobileImageOnCanvas(nextIdx);
  } else if (currentFiles.length > 0) {
    previewFileOnCanvas(Math.min(activePreviewIndex, currentFiles.length - 1));
  } else {
    resetCanvas();
  }

  // Delete from backend session and disk
  if (targetSession && target && target.filename) {
    try {
      await fetch(`/api/mobile/delete/${targetSession}/${encodeURIComponent(target.filename)}`, {
        method: 'POST'
      });
    } catch (err) {
      console.error('Failed to delete mobile image on server:', err);
    }
  }
}

async function clearUploadedFiles() {
  if (currentMobileSession && currentMobileImages.length > 0) {
    const sessionToClear = currentMobileSession;
    const imagesToClear = [...currentMobileImages];
    for (const img of imagesToClear) {
      try {
        await fetch(`/api/mobile/delete/${sessionToClear}/${encodeURIComponent(img.filename)}`, { method: 'POST' });
      } catch (e) {
        console.warn('Failed to delete on clear:', e);
      }
    }
  }

  currentFiles = [];
  currentMobileImages = [];
  currentSampleNames = [];
  currentAudit = null;
  isClaheView = false;
  activePreviewIndex = 0;
  activePreviewType = 'file';
  const fileInputEl = document.getElementById('fileInput');
  if (fileInputEl) fileInputEl.value = '';
  renderUploadPreviews();
  updateModalReceivedThumbs();
  resetCanvas();
}

function resetCanvas() {
  isClaheView = false;
  const btnClahe = document.getElementById('btnToggleClahe');
  if (btnClahe) {
    btnClahe.classList.remove('active');
    btnClahe.style.display = 'none';
  }
  loadedImage = null;
  ocrBoxes = [];
  labelCanvas.width = 600;
  labelCanvas.height = 360;
  ctx.clearRect(0, 0, 600, 360);
  ctx.fillStyle = '#f8fafc';
  ctx.fillRect(0, 0, 600, 360);
  ctx.strokeStyle = '#e2e8f0';
  ctx.strokeRect(10, 10, 580, 340);
  ctx.fillStyle = '#94a3b8';
  ctx.font = '500 14px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('No image selected — drop files above', 300, 180);
  ctx.textAlign = 'left';
  document.getElementById('canvasStats').textContent = 'Canvas ready';
}

function renderPdfPlaceholder(file, angleNum = 1) {
  loadedImage = null;
  ocrBoxes = [];
  labelCanvas.width = 600;
  labelCanvas.height = 360;
  ctx.clearRect(0, 0, 600, 360);
  ctx.fillStyle = '#f8fafc';
  ctx.fillRect(0, 0, 600, 360);

  ctx.strokeStyle = '#cbd5e1';
  ctx.lineWidth = 2;
  ctx.strokeRect(10, 10, 580, 340);

  ctx.fillStyle = '#ef4444';
  ctx.font = 'bold 30px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(`📄 PDF DOCUMENT • ANGLE ${angleNum}`, 300, 135);

  ctx.fillStyle = '#1e293b';
  ctx.font = '600 16px Inter, sans-serif';
  const truncatedName = file.name.length > 40 ? file.name.substring(0, 37) + '...' : file.name;
  ctx.fillText(truncatedName, 300, 180);

  ctx.fillStyle = '#64748b';
  ctx.font = '13px Inter, sans-serif';
  ctx.fillText(`${(file.size / (1024 * 1024)).toFixed(2)} MB • Ready for Multi-Angle Inspection`, 300, 210);

  ctx.fillStyle = '#4f46e5';
  ctx.font = '500 12px Inter, sans-serif';
  ctx.fillText('Click "Analyze Product Compliance" to inspect all pages & angles', 300, 240);
  ctx.textAlign = 'left';
}

// Toggle Calibration Mode
function toggleCalibMode() {
  const mode = document.getElementById('calibMode').value;
  document.getElementById('dimFields').style.display = mode === 'dimensions' ? 'grid' : 'none';
  document.getElementById('refFields').style.display = mode === 'reference_object' ? 'grid' : 'none';
}

// Load Image onto Canvas
function loadImageOntoCanvas(imgSrc) {
  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    ocrBoxes = [];
    renderCanvas();
    document.getElementById('canvasStats').textContent = `${img.naturalWidth} × ${img.naturalHeight} px`;
  };
  img.src = imgSrc;
}

// Render Canvas
function renderCanvas(hoveredBox = null) {
  if (!loadedImage) return;

  const container = document.getElementById('canvasContainer');
  const maxWidth = container.clientWidth - 20;
  const maxHeight = 650;

  let scale = Math.min(maxWidth / loadedImage.naturalWidth, maxHeight / loadedImage.naturalHeight, 1.0);
  labelCanvas.width = loadedImage.naturalWidth * scale;
  labelCanvas.height = loadedImage.naturalHeight * scale;

  ctx.clearRect(0, 0, labelCanvas.width, labelCanvas.height);
  ctx.drawImage(loadedImage, 0, 0, labelCanvas.width, labelCanvas.height);

  // Draw Bounding Boxes
  ocrBoxes.forEach(box => {
    const isHovered = (box === hoveredBox);
    const color = box.color || '#06b6d4';

    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = isHovered ? 3 : 1.5;
    ctx.fillStyle = isHovered ? color.replace(')', ', 0.25)').replace('rgb', 'rgba') : color.replace(')', ', 0.10)').replace('rgb', 'rgba');

    if (box.polygon && box.polygon.length >= 4) {
      ctx.beginPath();
      ctx.moveTo(box.polygon[0][0] * scale, box.polygon[0][1] * scale);
      for (let i = 1; i < box.polygon.length; i++) {
        ctx.lineTo(box.polygon[i][0] * scale, box.polygon[i][1] * scale);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.strokeRect(box.x * scale, box.y * scale, box.width * scale, box.height * scale);
      ctx.fillRect(box.x * scale, box.y * scale, box.width * scale, box.height * scale);
    }

    // Draw small field tag if present
    if (box.fieldTag) {
      ctx.font = '600 10px Inter, -apple-system, sans-serif';
      const textWidth = ctx.measureText(box.fieldTag.toUpperCase()).width;
      const tagX = box.x * scale;
      const tagY = Math.max(14, box.y * scale - 4);
      
      // Crisp dark pill backdrop
      ctx.fillStyle = 'rgba(8, 9, 10, 0.88)';
      ctx.fillRect(tagX - 3, tagY - 11, textWidth + 6, 14);
      
      // Border outline on pill
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.strokeRect(tagX - 3, tagY - 11, textWidth + 6, 14);

      // Text
      ctx.fillStyle = color;
      ctx.fillText(box.fieldTag.toUpperCase(), tagX, tagY);
    }

    ctx.restore();
  });
}

// Run Compliance Audit
async function runAudit() {
  if (currentFiles.length === 0 && currentSampleNames.length === 0 && currentMobileImages.length === 0) {
    alert('Please select or upload package label image(s) to analyze.');
    return;
  }

  const pkgWidth = parseFloat(document.getElementById('pkgWidth').value);
  const pkgHeight = parseFloat(document.getElementById('pkgHeight').value);
  const pkgDepth = parseFloat(document.getElementById('pkgDepth').value || '0');

  if (isNaN(pkgWidth) || pkgWidth < 5 || pkgWidth > 2500 || isNaN(pkgHeight) || pkgHeight < 5 || pkgHeight > 2500) {
    alert('Package dimensions must be positive values between 5 mm and 2500 mm.');
    return;
  }

  if (mobilePollTimer) {
    clearInterval(mobilePollTimer);
    mobilePollTimer = null;
  }

  loadingOverlay.style.display = 'block';
  document.getElementById('btnRunAudit').disabled = true;

  const formData = new FormData();
  if (currentFiles.length > 0) {
    currentFiles.forEach(file => {
      formData.append('files', file);
    });
  }
  if (currentMobileImages.length > 0) {
    formData.append('sample_filenames', currentMobileImages.map(m => m.filename).join(','));
  } else if (currentFiles.length === 0 && currentSampleNames.length > 0) {
    formData.append('sample_filenames', currentSampleNames.join(','));
  }

  const calibMode = document.getElementById('calibMode').value;
  formData.append('calibration_mode', calibMode);
  formData.append('package_type', document.getElementById('pkgType').value);
  formData.append('package_width_mm', pkgWidth);
  formData.append('package_height_mm', pkgHeight);
  formData.append('package_depth_mm', pkgDepth);
  formData.append('reference_object_id', document.getElementById('refObjectId').value);
  formData.append('reference_pixel_size', document.getElementById('refPixelSize').value);

  try {
    const res = await fetch('/api/audit', {
      method: 'POST',
      headers: {
        ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {})
      },
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Audit failed');
    }

    const audit = await res.json();
    currentAudit = audit;
    displayAuditResults(audit);
  } catch (err) {
    alert(`Audit Error: ${err.message}`);
    console.error(err);
  } finally {
    loadingOverlay.style.display = 'none';
    document.getElementById('btnRunAudit').disabled = false;
  }
}

// Display Audit Results
function displayAuditResults(audit) {
  // Reveal results container and hide empty awaiting card
  const awaitingCard = document.getElementById('awaitingCard');
  if (awaitingCard) awaitingCard.style.display = 'none';
  const resultsContainer = document.getElementById('resultsContainer');
  if (resultsContainer) resultsContainer.style.display = 'block';

  // 1. Executive Verdict Banner
  const banner = document.getElementById('verdictBanner');
  banner.className = `kpi-card kpi-verdict-${audit.verdict} verdict-banner verdict-${audit.verdict}`;
  document.getElementById('verdictText').textContent = audit.verdict.replace('_', ' ');
  document.getElementById('scoreValue').textContent = `${audit.overall_score.toFixed(0)}%`;
  document.getElementById('cntPass').textContent = `${audit.summary.passed} Passed`;
  document.getElementById('cntWarn').textContent = `${audit.summary.warnings} Warnings`;
  document.getElementById('cntFail').textContent = `${audit.summary.failed} Violations`;

  // Render Statutory Exemption Badges
  const exemptionPills = document.getElementById('exemptionPills');
  if (exemptionPills) {
    const exemptions = audit.exemptions || (audit.summary && audit.summary.exemptions) || [];
    if (exemptions.length > 0) {
      exemptionPills.innerHTML = exemptions.map(e => `
        <span class="exemption-pill" title="Statutory Exemption applied under Legal Metrology Rules">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          ${escapeHtml(e)}
        </span>
      `).join('');
      exemptionPills.style.display = 'flex';
    } else {
      exemptionPills.innerHTML = '';
      exemptionPills.style.display = 'none';
    }
  }

  // Render Optical Clarity / Glare Warning Banner & CLAHE Telemetry
  const clarityBanner = document.getElementById('clarityBanner');
  if (clarityBanner) {
    const ocrConf = audit.ocr_confidence !== undefined ? audit.ocr_confidence : (audit.summary && audit.summary.ocr_confidence);
    const glarePct = audit.total_glare_percentage !== undefined ? audit.total_glare_percentage : (audit.angles && audit.angles[0] ? audit.angles[0].glare_percentage : 0);
    const recoveredBlocks = audit.blocks_recovered_by_clahe || 0;

    if (glarePct > 3.0 || (ocrConf !== undefined && ocrConf < 0.50)) {
      let glareMsg = '';
      if (glarePct > 0) {
        glareMsg = ` <b>${glarePct.toFixed(1)}% Specular Glare hot-spots detected:</b> OpenCV CLAHE (CIE LAB L-Channel) and Telea inpainting applied to equalize contrast. ${recoveredBlocks > 0 ? `<b>${recoveredBlocks} obscured text block${recoveredBlocks === 1 ? '' : 's'} successfully recovered.</b>` : ''}`;
      } else {
        glareMsg = ` <b>Low Optical Clarity (${Math.round(ocrConf * 100)}%) Detected:</b> Reflections or blur may affect OCR confidence.`;
      }
      clarityBanner.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <span>${glareMsg} Toggle <b>[✨ Anti-Glare (CLAHE)]</b> on the canvas above to view the enhanced image.</span>
      `;
      clarityBanner.style.display = 'flex';
    } else {
      clarityBanner.style.display = 'none';
    }
  }

  // Configure CLAHE Toggle Button
  const btnToggleClahe = document.getElementById('btnToggleClahe');
  if (btnToggleClahe) {
    const hasClahe = (audit.angles && audit.angles.some(a => a.clahe_image_url)) || audit.clahe_image_url;
    if (hasClahe) {
      btnToggleClahe.style.display = 'inline-flex';
      btnToggleClahe.classList.toggle('active', isClaheView);
      if (isClaheView) {
        btnToggleClahe.innerHTML = `<span>⚡ CLAHE Anti-Glare (ON)</span>`;
      } else {
        btnToggleClahe.innerHTML = `<span>✨ Anti-Glare (CLAHE)</span>`;
      }
    } else {
      btnToggleClahe.style.display = 'none';
    }
  }

  // 2. PDP Metrics
  const pdp = audit.pdp;
  document.getElementById('pdpAreaVal').textContent = `${pdp.pdp_area_sqcm.toFixed(1)} cm²`;
  document.getElementById('pdpFormula').textContent = pdp.calculation_formula;
  document.getElementById('pdpMinFontVal').textContent = `≥ ${pdp.required_min_font_height_mm.toFixed(1)} mm`;
  document.getElementById('scaleFactorVal').textContent = `${audit.calibration.mm_per_pixel.toFixed(3)} mm/px`;

  // 3. Render Angle Tabs & Load Active Angle
  renderAngleTabs(audit);
  activeAngleId = (audit.angles && audit.angles.length > 0) ? audit.angles[0].angle_id : 1;
  switchAngleView(activeAngleId);

  // 4. Populate Mandatory Declarations Table
  populateDeclarationsTable(audit);

  // 5. Populate Rules & Penalty Table
  populateRulesTable(audit);

  // 6. Enable PDF Download Button & Conditional Govt Reporting
  btnDownloadPdf.style.display = 'inline-flex';

  const btnReportGovt = document.getElementById('btnReportGovt');
  const grievanceNotice = document.getElementById('grievanceNotice');
  const isNonCompliant = (audit.verdict === 'NON_COMPLIANT' || (audit.summary && audit.summary.failed > 0));

  if (isNonCompliant) {
    if (btnReportGovt) btnReportGovt.style.display = 'inline-flex';
    if (grievanceNotice) grievanceNotice.style.display = 'block';
  } else {
    if (btnReportGovt) btnReportGovt.style.display = 'none';
    if (grievanceNotice) grievanceNotice.style.display = 'none';
  }
}

function renderAngleTabs(audit) {
  const container = document.getElementById('angleTabsContainer');
  if (!audit.angles || audit.angles.length <= 1) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.innerHTML = '';
  container.style.display = 'flex';

  audit.angles.forEach((angle) => {
    const btn = document.createElement('button');
    btn.className = `btn btn-secondary angle-tab-btn ${angle.angle_id === activeAngleId ? 'active-angle-btn' : ''}`;
    btn.id = `angle-btn-${angle.angle_id}`;
    btn.style.cssText = 'padding: 0.3rem 0.65rem; font-size: 0.74rem; border-radius: 4px; display: inline-flex; align-items: center; gap: 0.4rem; white-space: nowrap; cursor: pointer; transition: all 0.15s;';
    btn.innerHTML = `<span>${escapeHtml(angle.label)}</span> <span style="font-size:0.65rem; opacity:0.75; font-family:var(--font-mono);">(${angle.ocr_blocks.length})</span>`;
    btn.onclick = () => switchAngleView(angle.angle_id);
    container.appendChild(btn);
  });
}

function switchAngleView(angleId) {
  activeAngleId = angleId;
  if (!currentAudit) return;

  // Highlight active tab
  document.querySelectorAll('.angle-tab-btn').forEach(btn => {
    btn.classList.remove('active-angle-btn');
    btn.style.borderColor = 'var(--border-color)';
    btn.style.background = 'var(--bg-subtle)';
    btn.style.color = 'var(--text-secondary)';
  });
  const activeBtn = document.getElementById(`angle-btn-${angleId}`);
  if (activeBtn) {
    activeBtn.classList.add('active-angle-btn');
    activeBtn.style.borderColor = 'var(--accent-primary)';
    activeBtn.style.background = 'var(--accent-blue-subtle)';
    activeBtn.style.color = 'var(--text-primary)';
  }

  // Find target angle data
  let targetAngle = currentAudit.angles && currentAudit.angles.find(a => a.angle_id === angleId);
  if (!targetAngle && currentAudit.angles && currentAudit.angles.length > 0) {
    targetAngle = currentAudit.angles[0];
  }

  const imageUrl = (isClaheView && targetAngle && targetAngle.clahe_image_url)
    ? targetAngle.clahe_image_url
    : (targetAngle ? targetAngle.image_url : currentAudit.image_url);
  const blocks = targetAngle ? targetAngle.ocr_blocks : currentAudit.all_ocr_blocks;
  const fields = targetAngle ? targetAngle.extracted_fields : currentAudit.extracted_fields;

  // Load image onto canvas and render boxes
  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    prepareCanvasBoxesForAngle(blocks, fields, currentAudit.rule_evaluations);
    renderCanvas();
    const angleLabel = targetAngle ? targetAngle.label : 'View';
    const claheTag = (isClaheView && targetAngle && targetAngle.clahe_image_url) ? ' [CLAHE View]' : '';
    const glareInfo = (targetAngle && targetAngle.glare_percentage !== undefined) ? ` | Glare: ${targetAngle.glare_percentage.toFixed(1)}%` : '';
    document.getElementById('canvasStats').textContent = `${angleLabel}${claheTag}: ${img.naturalWidth} × ${img.naturalHeight} px | ${blocks.length} text elements${glareInfo}`;
  };
  img.src = imageUrl;
}

function prepareCanvasBoxesForAngle(blocks, extractedFields, ruleEvaluations) {
  ocrBoxes = [];
  const fieldBoxMap = new Map();
  for (const [key, field] of Object.entries(extractedFields || {})) {
    if (field && field.bbox) {
      fieldBoxMap.set(`${Math.round(field.bbox.x)}_${Math.round(field.bbox.y)}`, { key, field });
    }
  }

  const evalStatusMap = new Map();
  (ruleEvaluations || []).forEach(ev => {
    evalStatusMap.set(ev.field_target, ev.status);
  });

  (blocks || []).forEach(block => {
    const bboxKey = `${Math.round(block.bbox.x)}_${Math.round(block.bbox.y)}`;
    const matched = fieldBoxMap.get(bboxKey);

    let color = '#7170ff'; // Linear Violet for detected text
    let fieldTag = '';

    if (matched) {
      fieldTag = matched.field.label;
      const status = evalStatusMap.get(matched.key) || 'PASS';
      if (status === 'FAIL') color = '#dc2626'; // Linear Red (Violation)
      else if (status === 'WARNING') color = '#eab308'; // Linear Amber (Warning)
      else color = '#27a644'; // Linear Emerald (Compliant)
    } else if (block.source_enhancement === 'clahe') {
      color = '#06b6d4'; // Cyan for blocks recovered by CLAHE
      fieldTag = 'CLAHE';
    }

    ocrBoxes.push({
      x: block.bbox.x,
      y: block.bbox.y,
      width: block.bbox.width,
      height: block.bbox.height,
      polygon: block.bbox.polygon,
      text: block.text,
      confidence: block.confidence,
      height_mm: block.height_mm,
      fieldTag: fieldTag,
      color: color,
      sourceEnhancement: block.source_enhancement || 'raw'
    });
  });
}

function populateDeclarationsTable(audit) {
  const tbody = document.getElementById('declarationsTableBody');
  tbody.innerHTML = '';

  const mandatoryKeys = [
    { key: 'commodity_name', name: 'Commodity Name', clause: 'Rule 6(1)(b)' },
    { key: 'net_quantity', name: 'Net Quantity', clause: 'Rule 6(1)(c)' },
    { key: 'mrp', name: 'MRP (Incl. Taxes)', clause: 'Rule 6(1)(e)' },
    { key: 'unit_sale_price', name: 'Unit Sale Price', clause: 'Rule 6(1)(e)' },
    { key: 'mfg_date', name: 'Mfg / Pkd Date', clause: 'Rule 6(1)(d)' },
    { key: 'manufacturer', name: 'Manufacturer / Packer', clause: 'Rule 6(1)(a)' },
    { key: 'consumer_care', name: 'Consumer Care', clause: 'Rule 6(1)(f)' },
    { key: 'country_of_origin', name: 'Country of Origin', clause: 'Rule 6(10)' }
  ];

  const evalsMap = new Map();
  audit.rule_evaluations.forEach(ev => evalsMap.set(ev.field_target, ev));

  mandatoryKeys.forEach(item => {
    const field = audit.extracted_fields[item.key];
    const ev = evalsMap.get(item.key);
    const status = ev ? ev.status : (field ? 'PASS' : 'FAIL');

    let angleBadge = '<span style="color:var(--text-muted); font-size:0.75rem;">--</span>';
    if (field && field.source_angle) {
      angleBadge = `<span style="font-size: 0.7rem; background: var(--accent-blue-subtle); color: var(--text-cyan); padding: 2px 7px; border-radius: 4px; border: 1px solid var(--accent-blue-border); white-space: nowrap; font-weight: 600; font-family: var(--font-mono);">${escapeHtml(field.source_angle)}</span>`;
    } else if (field) {
      angleBadge = `<span style="font-size: 0.7rem; background: rgba(255,255,255,0.06); color: var(--text-secondary); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono);">Primary</span>`;
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><b>${item.name}</b><br/><span style="font-size:0.65rem;color:var(--text-muted);font-family:var(--font-mono);">${item.clause}</span></td>
      <td>${field ? escapeHtml(field.raw_text) : '<span style="color:var(--text-red);">Not Detected</span>'}</td>
      <td>${angleBadge}</td>
      <td>${field && field.font_height_mm ? `<span style="font-family:var(--font-mono);">${field.font_height_mm.toFixed(2)} mm</span>` : '--'}</td>
      <td><span class="status-badge badge-${status}">${status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function populateRulesTable(audit) {
  const tbody = document.getElementById('rulesTableBody');
  tbody.innerHTML = '';

  audit.rule_evaluations.forEach(ev => {
    const tr = document.createElement('tr');
    const penaltyHtml = ev.penalty_risk 
      ? `<div style="font-size:0.7rem;color:var(--text-red);margin-top:4px;display:inline-flex;align-items:center;gap:4px;background:var(--accent-red-subtle);padding:2px 6px;border-radius:4px;border:1px solid var(--accent-red-border);font-family:var(--font-mono);"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ${escapeHtml(ev.penalty_risk)}</div>` 
      : '';

    tr.innerHTML = `
      <td><b style="font-family:var(--font-mono);font-size:0.75rem;">${ev.clause}</b></td>
      <td>${ev.title}</td>
      <td>
        <div>${escapeHtml(ev.message)}</div>
        <div style="font-size:0.7rem;color:var(--text-secondary);margin-top:3px;font-family:var(--font-mono);">
          <b>Measured:</b> ${escapeHtml(ev.measured_value || 'N/A')} | <b>Expected:</b> ${escapeHtml(ev.expected_value || 'N/A')}
        </div>
        ${penaltyHtml}
      </td>
      <td><span class="status-badge badge-${ev.status}">${ev.status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// Toggle OpenCV CLAHE Anti-Glare View on Canvas
function toggleClaheView() {
  isClaheView = !isClaheView;
  const btn = document.getElementById('btnToggleClahe');
  if (btn) {
    btn.classList.toggle('active', isClaheView);
    if (isClaheView) {
      btn.innerHTML = `<span>⚡ CLAHE Anti-Glare (ON)</span>`;
    } else {
      btn.innerHTML = `<span>✨ Anti-Glare (CLAHE)</span>`;
    }
  }
  if (!currentAudit) return;
  switchAngleView(activeAngleId);
}

// Canvas Tooltip & Hover
function setupCanvasInteraction() {
  labelCanvas.addEventListener('mousemove', (e) => {
    if (!loadedImage || ocrBoxes.length === 0) return;

    const rect = labelCanvas.getBoundingClientRect();
    const scaleX = labelCanvas.width / rect.width;
    const scaleY = labelCanvas.height / rect.height;
    const mouseX = (e.clientX - rect.left) * scaleX;
    const mouseY = (e.clientY - rect.top) * scaleY;

    let hovered = null;
    const imgScale = labelCanvas.width / loadedImage.naturalWidth;

    for (let box of ocrBoxes) {
      const bx = box.x * imgScale;
      const by = box.y * imgScale;
      const bw = box.width * imgScale;
      const bh = box.height * imgScale;

      if (mouseX >= bx && mouseX <= bx + bw && mouseY >= by && mouseY <= by + bh) {
        hovered = box;
        break;
      }
    }

    if (hovered) {
      canvasTooltip.style.display = 'block';
      canvasTooltip.style.left = `${e.pageX + 15}px`;
      canvasTooltip.style.top = `${e.pageY + 10}px`;

      const claheBadge = (hovered.sourceEnhancement === 'clahe') 
        ? '<div style="font-size:0.68rem;color:#06b6d4;font-weight:600;margin-top:3px;display:flex;align-items:center;gap:3px;"><span>✨</span> Recovered via OpenCV CLAHE Anti-Glare</div>' 
        : '';

      canvasTooltip.innerHTML = `
        <div style="font-weight:600;font-size:0.75rem;color:var(--text-cyan);letter-spacing:0.02em;">${hovered.fieldTag || 'Detected Text Block'}</div>
        <div style="font-size:0.8rem;margin:3px 0;color:var(--text-primary);font-family:var(--font-mono);">"${escapeHtml(hovered.text)}"</div>
        <div style="font-size:0.68rem;color:var(--text-muted);font-family:var(--font-mono);">
          Confidence: ${(hovered.confidence * 100).toFixed(0)}% | Height: ${hovered.height_mm ? `${hovered.height_mm.toFixed(2)} mm` : `${hovered.height} px`}
        </div>
        ${claheBadge}
      `;
      renderCanvas(hovered);
    } else {
      canvasTooltip.style.display = 'none';
      renderCanvas(null);
    }
  });

  labelCanvas.addEventListener('mouseleave', () => {
    canvasTooltip.style.display = 'none';
    renderCanvas(null);
  });
}

// Download PDF Report
function downloadCurrentAuditPdf() {
  if (!currentAudit) return;
  window.open(`/api/reports/${currentAudit.audit_id}`, '_blank');
}

// Escalate Non-Compliance: Report to Official Govt Portal
function reportToGovtPortal() {
  if (!currentAudit) return;
  // Automatically copy draft to clipboard so user has it ready
  copyViolationDraft(false);
  // Redirect / open official National Consumer Helpline (NCH / INGRAM) portal
  window.open('https://consumerhelpline.gov.in/', '_blank', 'noopener,noreferrer');
}

// Copy concise violation summary for pasting into consumer grievance portal
function copyViolationDraft(showSuccessToast = true) {
  if (!currentAudit) return;
  const commodity = currentAudit.extracted_fields?.commodity_name?.value || 'Packaged Commodity';
  const mfg = currentAudit.extracted_fields?.manufacturer?.value || 'Unspecified Manufacturer';
  const violations = (currentAudit.rule_evaluations || [])
    .filter(r => r.status === 'FAIL')
    .map((r, i) => `${i + 1}. [${r.clause}] ${r.rule_name}: ${r.reason}`)
    .join('\n');

  const draftText = `LEGAL METROLOGY COMPLAINT SUMMARY:
Product Name: ${commodity}
Manufacturer / Packer: ${mfg}
SYNX Compliance Score: ${currentAudit.overall_score ? currentAudit.overall_score.toFixed(0) : 0}%
Statutory Violations (Legal Metrology Act, 2009 / Packaged Commodities Rules, 2011):
${violations || 'Mandatory statutory declarations missing or non-compliant under Rule 6.'}

Audit Reference ID: ${currentAudit.audit_id || 'N/A'}`;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(draftText).then(() => {
      const btnText = document.getElementById('copyDraftBtnText');
      if (btnText) {
        const orig = btnText.textContent;
        btnText.textContent = '✓ Summary Copied!';
        setTimeout(() => { btnText.textContent = orig; }, 2500);
      }
    }).catch(err => {
      console.warn('Clipboard write failed:', err);
    });
  }
}

// Rulebook Modal
async function openRulebookModal() {
  try {
    const res = await fetch('/api/rules');
    const rulesJson = await res.json();
    document.getElementById('rulebookJsonEditor').value = JSON.stringify(rulesJson, null, 2);
    document.getElementById('rulebookModal').style.display = 'flex';
  } catch (err) {
    alert('Failed to fetch rulebook JSON.');
  }
}

function closeRulebookModal() {
  document.getElementById('rulebookModal').style.display = 'none';
}

async function saveRulebook() {
  const text = document.getElementById('rulebookJsonEditor').value;
  try {
    const parsed = JSON.parse(text);
    const res = await fetch('/api/rules', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(parsed)
    });

    if (res.ok) {
      alert('Digital Rulebook updated and hot-reloaded successfully!');
      closeRulebookModal();
      if (currentAudit) runAudit();
    } else {
      const err = await res.json();
      alert(`Failed to save: ${err.detail}`);
    }
  } catch (err) {
    alert(`Invalid JSON format: ${err.message}`);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ==========================================
// 📱 Mobile Phone Camera Companion (Field Inspector)
// ==========================================
let mobilePollTimer = null;
let currentMobileSession = null;
let currentMobileUrls = { network: '', local: '' };

async function openMobileConnectModal() {
  const modal = document.getElementById('mobileConnectModal');
  modal.style.display = 'flex';
  document.getElementById('mobileSyncStatus').innerHTML = '<span class="spinner"></span> Generating session...';

  updateModalReceivedThumbs();

  try {
    const res = await fetch('/api/mobile/session', { method: 'POST' });
    const data = await res.json();
    currentMobileSession = data.session_id;
    currentMobileUrls = {
      network: data.mobile_url,
      local: data.localhost_url || data.mobile_url
    };

    // Render QR Code
    const qrContainer = document.getElementById('mobileQrCode');
    qrContainer.innerHTML = '';
    if (window.QRCode) {
      new QRCode(qrContainer, {
        text: data.mobile_url,
        width: 170,
        height: 170,
        colorDark: '#0b0f19',
        colorLight: '#ffffff',
        correctLevel: QRCode.CorrectLevel.M
      });
    }

    const linkEl = document.getElementById('mobileDirectLink');
    linkEl.href = data.mobile_url;
    linkEl.textContent = data.mobile_url;

    const statusEl = document.getElementById('mobileSyncStatus');
    if (currentMobileImages.length > 0) {
      statusEl.innerHTML = `<span class="spinner"></span> Received <b>${currentMobileImages.length}</b> angle(s) from phone! Tap 'Transmit All' on phone or click 'Audit' below.`;
    } else {
      statusEl.innerHTML = '<span class="spinner"></span> Waiting for photo transmission from mobile device...';
    }

    // Start polling for uploaded photo
    startMobilePolling(data.session_id);
  } catch (err) {
    alert('Failed to initialize mobile session: ' + err.message);
  }
}

function updateModalReceivedThumbs() {
  const previewSec = document.getElementById('mobileReceivedSection');
  const thumbsBox = document.getElementById('mobileReceivedThumbs');
  const countSpan = document.getElementById('mobileReceivedCount');
  const btnAudit = document.getElementById('btnForceAuditMobile');
  const syncStatus = document.getElementById('mobileSyncStatus');

  if (!previewSec || !thumbsBox) return;

  if (currentMobileImages.length === 0) {
    previewSec.style.display = 'none';
    if (btnAudit) btnAudit.style.display = 'none';
    if (syncStatus && (!currentMobileSession || syncStatus.textContent.includes('Received') || syncStatus.textContent.includes('angle'))) {
      syncStatus.innerHTML = '<span class="spinner"></span> Waiting for photo transmission from mobile device...';
    }
    return;
  }

  previewSec.style.display = 'block';
  if (countSpan) countSpan.textContent = currentMobileImages.length;
  if (btnAudit) {
    btnAudit.style.display = 'inline-flex';
    btnAudit.textContent = `⚡ Audit Received Photos Now (${currentMobileImages.length})`;
  }
  if (syncStatus) {
    syncStatus.innerHTML = `<span class="spinner"></span> Received <b>${currentMobileImages.length}</b> angle(s) from phone! Tap 'Transmit All' on phone or click 'Audit' below.`;
  }

  thumbsBox.innerHTML = currentMobileImages.map((img, i) => `
    <div style="width: 56px; height: 56px; border-radius: 6px; overflow: hidden; border: 1.5px solid var(--accent-primary); position: relative; box-shadow: 0 1px 3px rgba(0,0,0,0.15);" title="Mobile Angle ${i+1} (${escapeHtml(img.filename)})">
      <button type="button" class="btn-del-modal" onclick="removeMobileUploadedFile(${i}, event)" title="Remove this snapped angle">&times;</button>
      <img src="${img.image_url}" style="width: 100%; height: 100%; object-fit: cover; cursor: pointer;" onclick="previewMobileImageOnCanvas(${i})" alt="Angle ${i+1}">
      <span style="position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.72); font-size: 8.5px; color: #fff; text-align: center; pointer-events: none;">Angle ${i+1}</span>
    </div>
  `).join('');
}

function openMobileViewInTab() {
  if (currentMobileUrls && currentMobileUrls.local) {
    window.open(currentMobileUrls.local, '_blank');
  } else if (currentMobileSession) {
    window.open(`/mobile?session=${currentMobileSession}`, '_blank');
  }
}

async function forceAuditMobilePhotos() {
  if (!currentMobileSession) return;
  const btn = document.getElementById('btnForceAuditMobile');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Processing...';
  }
  document.getElementById('mobileSyncStatus').innerHTML = '<span class="spinner"></span> Submitting session and analyzing package compliance...';
  try {
    await fetch(`/api/mobile/submit/${currentMobileSession}`, { method: 'POST' });
  } catch (err) {
    console.error('Failed to submit mobile session:', err);
  }
}

function closeMobileConnectModal() {
  document.getElementById('mobileConnectModal').style.display = 'none';
  if (currentMobileImages.length === 0 && mobilePollTimer) {
    clearInterval(mobilePollTimer);
    mobilePollTimer = null;
  }
}

function startMobilePolling(sessionId) {
  if (mobilePollTimer) clearInterval(mobilePollTimer);

  mobilePollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/mobile/poll/${sessionId}`);
      if (!res.ok) return;
      const data = await res.json();

      if (data.status === 'ready') {
        clearInterval(mobilePollTimer);
        mobilePollTimer = null;

        if (data.images && data.images.length > 0) {
          currentMobileImages = data.images;
        }
        const count = currentMobileImages.length || (data.filenames ? data.filenames.length : 1);
        const syncEl = document.getElementById('mobileSyncStatus');
        if (syncEl) {
          syncEl.innerHTML = `<span style="color:var(--text-green);font-weight:600;">✓ Connected:</span> ${count} photo(s) received. Processing on workstation...`;
        }
        setTimeout(() => {
          closeMobileConnectModal();
        }, 800);

        // Load primary image onto canvas and set filenames
        currentFiles = [];
        currentSampleNames = currentMobileImages.length > 0 
          ? currentMobileImages.map(img => img.filename)
          : (data.filenames || [data.filename]);
        document.querySelectorAll('.benchmark-btn').forEach(b => b.classList.remove('active'));

        renderUploadPreviews();

        if (currentMobileImages.length > 0) {
          previewMobileImageOnCanvas(0);
        } else if (data.image_url) {
          loadImageOntoCanvas(data.image_url);
        }

        // Trigger automatic compliance audit
        setTimeout(() => {
          runAuditWithUploadedFilenames(currentSampleNames);
        }, 400);
      } else if (data.status === 'has_images' || data.uploaded_count > 0 || (data.images && data.images.length > 0)) {
        const serverFilenames = (data.images || []).map(img => img.filename).join(',');
        const localFilenames = currentMobileImages.map(img => img.filename).join(',');

        if (serverFilenames !== localFilenames) {
          const prevLen = currentMobileImages.length;
          currentMobileImages = data.images || [];
          currentSampleNames = currentMobileImages.map(img => img.filename);

          renderUploadPreviews();
          updateModalReceivedThumbs();

          if (currentMobileImages.length > prevLen) {
            previewMobileImageOnCanvas(currentMobileImages.length - 1);
          } else if (currentMobileImages.length === 0) {
            resetCanvas();
          } else if (activePreviewType === 'mobile' && activePreviewIndex >= currentMobileImages.length) {
            previewMobileImageOnCanvas(currentMobileImages.length - 1);
          }
        }
      } else if (data.uploaded_count === 0 && currentMobileImages.length > 0) {
        currentMobileImages = [];
        currentSampleNames = [];
        renderUploadPreviews();
        updateModalReceivedThumbs();
        resetCanvas();
      }
    } catch (e) {
      console.error('Polling error:', e);
    }
  }, 1000);
}

async function runAuditWithUploadedFilenames(filenames) {
  if (!filenames || filenames.length === 0) return;
  if (mobilePollTimer) {
    clearInterval(mobilePollTimer);
    mobilePollTimer = null;
  }
  loadingOverlay.style.display = 'block';
  document.getElementById('btnRunAudit').disabled = true;

  const formData = new FormData();
  formData.append('sample_filenames', filenames.join(','));

  const calibMode = document.getElementById('calibMode').value;
  formData.append('calibration_mode', calibMode);
  formData.append('package_type', document.getElementById('pkgType').value);
  formData.append('package_width_mm', document.getElementById('pkgWidth').value);
  formData.append('package_height_mm', document.getElementById('pkgHeight').value);
  formData.append('package_depth_mm', document.getElementById('pkgDepth').value);
  formData.append('reference_object_id', document.getElementById('refObjectId').value);
  formData.append('reference_pixel_size', document.getElementById('refPixelSize').value);

  try {
    const res = await fetch('/api/audit', {
      method: 'POST',
      headers: {
        ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {})
      },
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Audit failed');
    }
    const audit = await res.json();
    currentAudit = audit;
    displayAuditResults(audit);
  } catch (err) {
    console.error(err);
    alert('Audit error: ' + err.message);
  } finally {
    loadingOverlay.style.display = 'none';
    document.getElementById('btnRunAudit').disabled = false;
  }
}

// ==========================================
// 📷 Webcam Capture Logic
// ==========================================
let webcamStream = null;

async function openWebcamModal() {
  const modal = document.getElementById('webcamModal');
  modal.style.display = 'flex';
  const video = document.getElementById('webcamVideo');

  try {
    webcamStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 } }
    });
    video.srcObject = webcamStream;
  } catch (err) {
    alert('Could not access webcam: ' + err.message);
    closeWebcamModal();
  }
}

function closeWebcamModal() {
  document.getElementById('webcamModal').style.display = 'none';
  if (webcamStream) {
    webcamStream.getTracks().forEach(track => track.stop());
    webcamStream = null;
  }
}

function captureWebcamPhoto() {
  const video = document.getElementById('webcamVideo');
  const snapCanvas = document.getElementById('webcamSnapCanvas');
  snapCanvas.width = video.videoWidth || 1280;
  snapCanvas.height = video.videoHeight || 720;
  const sCtx = snapCanvas.getContext('2d');
  sCtx.drawImage(video, 0, 0, snapCanvas.width, snapCanvas.height);

  snapCanvas.toBlob((blob) => {
    const file = new File([blob], `webcam_snap_${Date.now()}.jpg`, { type: 'image/jpeg' });
    currentFiles = [file];
    currentSampleNames = [];
    document.querySelectorAll('.benchmark-btn').forEach(b => b.classList.remove('active'));

    closeWebcamModal();

    const reader = new FileReader();
    reader.onload = (e) => {
      loadImageOntoCanvas(e.target.result);
      setTimeout(() => {
        runAudit();
      }, 400);
    };
    reader.readAsDataURL(file);
  }, 'image/jpeg', 0.92);
}

// ==========================================
// 🗄️ Relational SQL Audit Ledger Logic
// ==========================================
// 🗄️ Relational SQL Audit Ledger Logic
// ==========================================
let historySearchTimer = null;
let currentLedgerScope = 'mine';

async function openHistoryModal() {
  const modal = document.getElementById('historyModal');
  if (modal) modal.style.display = 'flex';

  const scopeTabs = document.getElementById('ledgerScopeTabs');
  const titleElem = document.getElementById('historyModalTitle');

  if (currentUser && authToken) {
    currentLedgerScope = 'mine';
    if (scopeTabs) scopeTabs.style.display = 'flex';
    updateScopeTabButtons();
    if (titleElem) {
      titleElem.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
        </svg>
        Statutory Inspection SQL Ledger &bull; <span style="font-size:0.85rem;color:var(--text-green);">${escapeHtml(currentUser.name)}</span>
      `;
    }
  } else {
    currentLedgerScope = 'all';
    if (scopeTabs) scopeTabs.style.display = 'none';
    if (titleElem) {
      titleElem.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
        </svg>
        Statutory Inspection SQL Ledger
      `;
    }
  }

  loadAuditHistory();
  loadSqlAnalytics();
}

function isInspectorRole(role) {
  if (!role) return false;
  const r = role.toLowerCase();
  return r.includes('inspector') || r.includes('chief') || r.includes('senior') || r.includes('admin');
}

function switchLedgerScope(scope) {
  if (scope === 'all') {
    if (!currentUser) {
      openLoginModal();
      return;
    }
    if (!isInspectorRole(currentUser.role)) {
      alert(`🔒 Access Restricted:\n\nYour current assigned role is "${currentUser.role}".\nOnly officers holding the Legal Metrology Inspector role are authorized to access department-wide inspection ledgers.\n\nYou can request promotion or assign roles from the "Officer Role Management" console.`);
      return;
    }
  }
  currentLedgerScope = scope;
  updateScopeTabButtons();
  loadAuditHistory();
}

function updateScopeTabButtons() {
  const btnMine = document.getElementById('btnScopeMine');
  const btnAll = document.getElementById('btnScopeAll');
  if (btnMine && btnAll) {
    const isInspector = currentUser && isInspectorRole(currentUser.role);
    if (!isInspector) {
      btnAll.innerHTML = '🔒 All Records (Inspector Only)';
      btnAll.title = 'Only officers holding the Legal Metrology Inspector role can access all department ledgers.';
      btnAll.style.opacity = '0.75';
    } else {
      btnAll.innerHTML = '🌐 All Department Records';
      btnAll.title = 'View all statutory inspections across all officers';
      btnAll.style.opacity = '1';
    }

    if (currentLedgerScope === 'mine') {
      btnMine.className = 'btn btn-sm btn-primary';
      btnAll.className = 'btn btn-sm btn-secondary';
    } else {
      btnMine.className = 'btn btn-sm btn-secondary';
      btnAll.className = 'btn btn-sm btn-primary';
    }
  }
}

function closeHistoryModal() {
  document.getElementById('historyModal').style.display = 'none';
}

function onHistorySearch() {
  if (historySearchTimer) clearTimeout(historySearchTimer);
  historySearchTimer = setTimeout(() => {
    const q = document.getElementById('historySearchInput').value;
    loadAuditHistory(q);
  }, 250);
}

async function loadSqlAnalytics() {
  const bar = document.getElementById('sqlAnalyticsBar');
  try {
    const headers = {};
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    const res = await fetch('/api/analytics', { headers });
    const data = await res.json();

    let officerFragment = '';
    if (data.officer_name) {
      officerFragment = `
        <span style="font-weight:600;color:var(--text-primary);">Officer: <span style="font-family:var(--font-mono);color:var(--text-green);">${escapeHtml(data.officer_name)}</span> (My Audits: <b style="color:var(--text-cyan);">${data.officer_audit_count || 0}</b>)</span>
        <span style="color:var(--border-strong);">|</span>
      `;
    }

    bar.innerHTML = `
      ${officerFragment}
      <span style="font-weight:600;color:var(--text-primary);">Total Recorded: <span style="font-family:var(--font-mono);color:var(--text-cyan);">${data.total_inspections}</span></span>
      <span style="color:var(--border-strong);">|</span>
      <span style="color:var(--text-secondary);">Compliance Rate: <b style="color:var(--text-green);font-family:var(--font-mono);">${data.compliance_rate_percent}%</b></span>
      <span style="color:var(--border-strong);">|</span>
      <span style="color:var(--text-muted);">Storage: <span style="font-family:var(--font-mono);color:var(--text-secondary);">SQLite / PostgreSQL Relational</span></span>
    `;
  } catch (err) {
    bar.innerHTML = '<span style="color:var(--text-muted);">SQL Database Online</span>';
  }
}

async function loadAuditHistory(searchQuery = '') {
  const tbody = document.getElementById('historyTableBody');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:1rem;"><span class="spinner"></span> Querying SQL tables...</td></tr>';

  try {
    let url = `/api/history?limit=50&scope=${encodeURIComponent(currentLedgerScope)}`;
    if (searchQuery && searchQuery.trim()) {
      url += `&search=${encodeURIComponent(searchQuery.trim())}`;
    }

    const headers = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }

    const res = await fetch(url, { headers });
    const records = await res.json();

    if (!records || records.length === 0) {
      if (currentLedgerScope === 'mine' && currentUser) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;">
              <div style="font-size:1.1rem;margin-bottom:0.4rem;">📋 No personal audits recorded yet</div>
              <div style="font-size:0.8rem;color:var(--text-secondary);max-width:480px;margin:0 auto;">
                No statutory audits have been logged under your officer profile (<b>${escapeHtml(currentUser.name)}</b>) yet.
                Run an inspection to log records under your badge, or click <b>"🌐 All Department Records"</b> above to view overall department ledgers.
              </div>
            </td>
          </tr>
        `;
      } else {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:1.5rem;">No historical inspection records found in SQL database. Run an audit to log entries!</td></tr>';
      }
      return;
    }

    tbody.innerHTML = '';
    records.forEach(item => {
      const dt = item.created_at ? item.created_at.replace('T', ' ').substring(0, 19) : '--';
      const commodity = item.commodity_name || '<i style="color:var(--text-muted);">Unidentified</i>';
      const mfg = item.manufacturer || '<i style="color:var(--text-muted);">Unspecified</i>';
      const score = item.overall_score ? `${item.overall_score.toFixed(0)}%` : '--%';
      const inspectorPill = item.inspector_name
        ? `<div style="font-size: 0.68rem; color: #059669; font-weight: 500; margin-top: 2px;">👮 ${escapeHtml(item.inspector_name)}</div>`
        : '';

      let badgeClass = 'badge-INFO';
      if (item.verdict === 'COMPLIANT') badgeClass = 'badge-PASS';
      else if (item.verdict === 'NON_COMPLIANT') badgeClass = 'badge-FAIL';
      else if (item.verdict === 'CONDITIONAL') badgeClass = 'badge-WARNING';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family:var(--font-mono);font-size:0.72rem;color:var(--text-secondary);">${dt}</td>
        <td>
          <b>${escapeHtml(commodity)}</b>
          ${inspectorPill}
        </td>
        <td style="font-size:0.75rem;">${escapeHtml(mfg)}</td>
        <td style="font-family:var(--font-mono);font-weight:600;">${score}</td>
        <td><span class="status-badge ${badgeClass}">${item.verdict}</span></td>
        <td style="white-space:nowrap;">
          <button class="btn btn-secondary" style="padding:2px 8px;font-size:0.7rem;height:24px;" onclick="loadHistoricalAudit('${item.audit_id}')">
            🔍 Inspect
          </button>
          <a href="/api/reports/${item.audit_id}" target="_blank" class="btn btn-primary" style="padding:2px 8px;font-size:0.7rem;height:24px;text-decoration:none;margin-left:4px;">
            📄 PDF
          </a>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-red);padding:1rem;">Failed to load SQL records: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function loadHistoricalAudit(auditId) {
  try {
    const res = await fetch(`/api/history/${auditId}`);
    if (!res.ok) throw new Error('Audit not found');
    const data = await res.json();

    if (data.audit_detail) {
      currentAudit = data.audit_detail;
      closeHistoryModal();
      displayAuditResults(currentAudit);
      document.getElementById('canvasStats').textContent = `Historical SQL Record: ${auditId.substring(0, 8)}`;
    } else {
      alert('Detailed JSON payload not available for this record.');
    }
  } catch (err) {
    alert('Failed to load historical audit: ' + err.message);
  }
}

// ==========================================
// 🛡️ Officer Directory & Role Management (RBAC)
// ==========================================
async function openRoleModal() {
  const modal = document.getElementById('roleModal');
  if (modal) modal.style.display = 'flex';
  loadUsersList();
}

function closeRoleModal() {
  const modal = document.getElementById('roleModal');
  if (modal) modal.style.display = 'none';
}

async function loadUsersList() {
  const tbody = document.getElementById('roleTableBody');
  const alertContainer = document.getElementById('roleAlertContainer');
  if (alertContainer) alertContainer.innerHTML = '';
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:1.5rem;"><span class="spinner"></span> Loading officer records...</td></tr>';

  try {
    const headers = {};
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    const res = await fetch('/api/users', { headers });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to fetch officers directory.');
    }
    const data = await res.json();
    const users = data.users || [];

    if (users.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:1.5rem;">No registered officers found.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    const isCallerInspector = currentUser && isInspectorRole(currentUser.role);

    users.forEach(u => {
      const isIns = isInspectorRole(u.role);
      const isSelf = currentUser && currentUser.id === u.id;
      const avatarLetter = (u.name || 'O').charAt(0).toUpperCase();
      const avatarHtml = u.picture
        ? `<img src="${escapeHtml(u.picture)}" style="width:28px;height:28px;border-radius:50%;object-fit:cover;">`
        : `<div style="width:28px;height:28px;border-radius:50%;background:#059669;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.75rem;">${avatarLetter}</div>`;

      const roleBadgeClass = isIns ? 'badge-PASS' : 'badge-INFO';
      const roleBadge = `<span class="status-badge ${roleBadgeClass}">${escapeHtml(u.role || 'Field Officer')}</span>`;

      let actionHtml = '';
      if (!isCallerInspector) {
        actionHtml = '<span style="font-size:0.75rem;color:var(--text-muted);">View Only</span>';
      } else if (isIns) {
        actionHtml = `
          <button class="btn btn-secondary" style="padding:2px 10px;font-size:0.72rem;height:26px;" onclick="changeUserRole(${u.id}, 'Field Officer')">
            Demote to Field Officer
          </button>
        `;
      } else {
        actionHtml = `
          <button class="btn btn-primary" style="padding:2px 10px;font-size:0.72rem;height:26px;" onclick="changeUserRole(${u.id}, 'Legal Metrology Inspector')">
            ⭐ Assign Inspector Role
          </button>
        `;
      }

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>
          <div style="display:flex;align-items:center;gap:8px;">
            ${avatarHtml}
            <div>
              <div style="font-weight:600;font-size:0.82rem;">${escapeHtml(u.name)} ${isSelf ? '<span style="font-size:0.68rem;color:var(--text-cyan);">(You)</span>' : ''}</div>
              <div style="font-size:0.68rem;color:var(--text-muted);">Joined: ${u.created_at ? u.created_at.substring(0, 10) : '--'}</div>
            </div>
          </div>
        </td>
        <td style="font-family:var(--font-mono);font-size:0.75rem;color:var(--text-secondary);">${escapeHtml(u.email)}</td>
        <td style="font-size:0.75rem;color:var(--text-muted);">${escapeHtml(u.department || 'Enforcement Division')}</td>
        <td>${roleBadge}</td>
        <td style="text-align:right;">${actionHtml}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-red);padding:1.5rem;">Error loading officers: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function changeUserRole(userId, newRole) {
  const alertContainer = document.getElementById('roleAlertContainer');
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

    const res = await fetch(`/api/users/${userId}/role`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ role: newRole })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to update role.');
    }

    const data = await res.json();
    if (alertContainer) {
      alertContainer.innerHTML = `
        <div style="padding:0.5rem 0.75rem;background:rgba(5,150,105,0.15);border:1px solid var(--text-green);border-radius:var(--radius-sm);color:var(--text-green);font-size:0.78rem;">
          ✓ ${escapeHtml(data.message)}
        </div>
      `;
    }

    // If updating self, update current state and UI
    if (currentUser && currentUser.id === userId) {
      currentUser.role = newRole;
      renderAuthUI(currentUser);
      updateScopeTabButtons();
    }

    loadUsersList();
  } catch (err) {
    if (alertContainer) {
      alertContainer.innerHTML = `
        <div style="padding:0.5rem 0.75rem;background:rgba(239,68,68,0.15);border:1px solid var(--text-red);border-radius:var(--radius-sm);color:var(--text-red);font-size:0.78rem;">
          ✕ ${escapeHtml(err.message)}
        </div>
      `;
    }
  }
}

// ==========================================
// 🔐 Google Authentication & Session Management
// ==========================================

async function initAuth() {
  // 1. Close dropdown on outside click
  document.addEventListener('click', (e) => {
    const badge = document.getElementById('userProfileBadge');
    if (badge && !badge.contains(e.target)) {
      hideUserDropdown();
    }
  });

  // 2. Check existing session token
  if (authToken) {
    try {
      const res = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        currentUser = data.user;
        renderAuthUI(currentUser);
      } else {
        authToken = null;
        currentUser = null;
        localStorage.removeItem('synx_auth_token');
        renderAuthUI(null);
      }
    } catch (e) {
      console.warn('[Auth] Session validation failed:', e);
      renderAuthUI(null);
    }
  } else {
    renderAuthUI(null);
  }

  // 3. Fetch Google OAuth Client configuration
  try {
    const res = await fetch('/api/auth/config');
    if (res.ok) {
      googleAuthConfig = await res.json();
      setupGoogleIdentityServices();
    }
  } catch (e) {
    console.warn('[Auth] Failed to load auth config:', e);
  }
}

function setupGoogleIdentityServices() {
  if (!googleAuthConfig) return;

  const notice = document.getElementById('googleConfigNotice');
  if (notice) {
    notice.style.display = googleAuthConfig.has_client_id ? 'none' : 'block';
  }

  if (window.google && window.google.accounts && googleAuthConfig.google_client_id) {
    try {
      google.accounts.id.initialize({
        client_id: googleAuthConfig.google_client_id,
        callback: handleGoogleCredentialResponse,
        auto_select: false,
        cancel_on_tap_outside: true
      });
    } catch (e) {
      console.warn('[Auth] GIS initialization error:', e);
    }
  }
}

function openLoginModal() {
  const modal = document.getElementById('loginModal');
  if (modal) modal.style.display = 'flex';

  // Render official Google Sign-In button if GIS is available
  if (window.google && window.google.accounts && googleAuthConfig && googleAuthConfig.google_client_id) {
    const container = document.getElementById('googleSignInDiv');
    if (container) {
      container.innerHTML = '';
      try {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        google.accounts.id.renderButton(container, {
          theme: currentTheme === 'dark' ? 'filled_black' : 'outline',
          size: 'large',
          type: 'standard',
          text: 'signin_with',
          shape: 'rectangular',
          logo_alignment: 'left',
          width: 280
        });
      } catch (e) {
        console.warn('[Auth] RenderButton error:', e);
      }
    }
  }
}

function closeLoginModal() {
  const modal = document.getElementById('loginModal');
  if (modal) modal.style.display = 'none';
}

async function handleGoogleCredentialResponse(response) {
  if (!response || !response.credential) {
    alert('Google sign-in did not return valid credentials.');
    return;
  }

  try {
    const res = await fetch('/api/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential: response.credential })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Google sign-in verification failed.');
    }

    const data = await res.json();
    authToken = data.token;
    currentUser = data.user;
    localStorage.setItem('synx_auth_token', authToken);

    renderAuthUI(currentUser);
    closeLoginModal();
  } catch (err) {
    alert(`Authentication Error: ${err.message}`);
  }
}

async function loginDemoInspector(name, email) {
  try {
    const res = await fetch('/api/auth/demo-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Demo login failed');
    }

    const data = await res.json();
    authToken = data.token;
    currentUser = data.user;
    localStorage.setItem('synx_auth_token', authToken);

    renderAuthUI(currentUser);
    closeLoginModal();
  } catch (err) {
    alert(`Demo Login Error: ${err.message}`);
  }
}

async function logoutUser() {
  if (authToken) {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
    } catch (e) {
      console.warn('[Auth] Logout network error:', e);
    }
  }

  authToken = null;
  currentUser = null;
  localStorage.removeItem('synx_auth_token');
  hideUserDropdown();
  renderAuthUI(null);

  if (window.google && window.google.accounts && window.google.accounts.id) {
    try {
      google.accounts.id.disableAutoSelect();
    } catch (e) {}
  }
}

function toggleUserDropdown(event) {
  if (event) event.stopPropagation();
  const menu = document.getElementById('userDropdownMenu');
  if (menu) {
    menu.style.display = (menu.style.display === 'none' || !menu.style.display) ? 'block' : 'none';
  }
}

function hideUserDropdown() {
  const menu = document.getElementById('userDropdownMenu');
  if (menu) menu.style.display = 'none';
}

function renderAuthUI(user) {
  const btnLogin = document.getElementById('btnOpenLoginModal');
  const badge = document.getElementById('userProfileBadge');
  const nameEl = document.getElementById('userDisplayName');
  const roleEl = document.getElementById('userRoleTag');
  const avatarContainer = document.getElementById('userAvatarContainer');

  const dropName = document.getElementById('dropdownUserName');
  const dropEmail = document.getElementById('dropdownUserEmail');
  const dropRole = document.getElementById('dropdownUserRole');

  if (user) {
    if (btnLogin) btnLogin.style.display = 'none';
    if (badge) badge.style.display = 'inline-flex';

    if (nameEl) nameEl.textContent = user.name || 'Inspector';
    if (roleEl) roleEl.textContent = user.role ? user.role.replace('Legal Metrology ', '') : 'Officer';

    if (avatarContainer) {
      if (user.picture) {
        avatarContainer.innerHTML = `<img src="${escapeHtml(user.picture)}" alt="${escapeHtml(user.name)}" referrerpolicy="no-referrer">`;
      } else {
        const initials = (user.name || 'IN').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
        avatarContainer.innerHTML = `<span id="userInitials">${initials}</span>`;
      }
    }

    if (dropName) dropName.textContent = user.name || 'Enforcement Inspector';
    if (dropEmail) dropEmail.textContent = user.email || '';
    if (dropRole) dropRole.textContent = user.role || 'Legal Metrology Inspector';
  } else {
    if (btnLogin) btnLogin.style.display = 'inline-flex';
    if (badge) badge.style.display = 'none';
    hideUserDropdown();
  }
}


