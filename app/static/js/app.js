// SYNX Legal Metrology Compliance Checker - Client Logic

let currentFiles = [];
let currentSampleNames = [];
let currentAudit = null;
let loadedImage = null;
let ocrBoxes = [];
let activeAngleId = 1;

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
  loadBenchmarkSamples();
  setupDropZone();
  setupCanvasInteraction();
});

// Theme Management (Institutional Light & Obsidian Dark)
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
  try {
    const res = await fetch('/api/samples');
    const samples = await res.json();
    sampleGrid.innerHTML = '';

    samples.forEach((s, idx) => {
      const btn = document.createElement('div');
      btn.className = 'benchmark-btn';
      btn.id = `sample-btn-${idx}`;
      btn.innerHTML = `
        <b>${s.title.split(':')[0]}</b>
        <div style="font-size: 0.65rem; color: #9ca3af;">${s.description.substring(0, 45)}...</div>
      `;
      btn.onclick = () => selectSample(s, btn);
      sampleGrid.appendChild(btn);
    });

    // Auto-select first sample for instant demo
    if (samples.length > 0) {
      selectSample(samples[0], document.getElementById('sample-btn-0'));
    }
  } catch (err) {
    console.error('Failed to load samples:', err);
    sampleGrid.innerHTML = '<div style="color: #ef4444; font-size: 0.75rem;">Failed to load benchmark samples.</div>';
  }
}

// Select a sample
function selectSample(sample, btnElement) {
  document.querySelectorAll('.benchmark-btn').forEach(b => b.classList.remove('active'));
  if (btnElement) btnElement.classList.add('active');

  currentSampleNames = [sample.filename];
  currentFiles = [];
  document.getElementById('angleTabsContainer').style.display = 'none';

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

function handleFileSelect(event) {
  if (event.target.files.length > 0) {
    handleFiles(event.target.files);
  }
}

function handleFiles(files) {
  currentFiles = Array.from(files);
  currentSampleNames = [];
  document.querySelectorAll('.benchmark-btn').forEach(b => b.classList.remove('active'));

  if (currentFiles.length > 0) {
    const reader = new FileReader();
    reader.onload = (e) => {
      loadImageOntoCanvas(e.target.result);
    };
    reader.readAsDataURL(currentFiles[0]);
    document.getElementById('canvasStats').textContent = `${currentFiles.length} side(s) selected - ready to scan`;
    document.getElementById('angleTabsContainer').style.display = 'none';
  }
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
      ctx.fillStyle = color;
      ctx.font = 'bold 10px sans-serif';
      ctx.fillText(box.fieldTag.toUpperCase(), (box.x * scale), Math.max(12, box.y * scale - 3));
    }

    ctx.restore();
  });
}

// Run Compliance Audit
async function runAudit() {
  if (currentFiles.length === 0 && currentSampleNames.length === 0) {
    alert('Please select or upload package label image(s).');
    return;
  }

  loadingOverlay.style.display = 'block';
  document.getElementById('btnRunAudit').disabled = true;

  const formData = new FormData();
  if (currentFiles.length > 0) {
    currentFiles.forEach(file => {
      formData.append('files', file);
    });
  } else if (currentSampleNames.length > 0) {
    formData.append('sample_filenames', currentSampleNames.join(','));
  }

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
  // 1. Executive Verdict Banner
  const banner = document.getElementById('verdictBanner');
  banner.className = `verdict-banner verdict-${audit.verdict}`;
  document.getElementById('verdictText').textContent = audit.verdict.replace('_', ' ');
  document.getElementById('scoreValue').textContent = `${audit.overall_score.toFixed(0)}%`;
  document.getElementById('cntPass').textContent = `${audit.summary.passed} Passed`;
  document.getElementById('cntWarn').textContent = `${audit.summary.warnings} Warnings`;
  document.getElementById('cntFail').textContent = `${audit.summary.failed} Violations`;

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

  // 6. Enable PDF Download Button
  btnDownloadPdf.style.display = 'inline-flex';
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

  const imageUrl = targetAngle ? targetAngle.image_url : currentAudit.image_url;
  const blocks = targetAngle ? targetAngle.ocr_blocks : currentAudit.all_ocr_blocks;
  const fields = targetAngle ? targetAngle.extracted_fields : currentAudit.extracted_fields;

  // Load image onto canvas and render boxes
  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    prepareCanvasBoxesForAngle(blocks, fields, currentAudit.rule_evaluations);
    renderCanvas();
    const angleLabel = targetAngle ? targetAngle.label : 'View';
    document.getElementById('canvasStats').textContent = `${angleLabel}: ${img.naturalWidth} × ${img.naturalHeight} px | ${blocks.length} text elements`;
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

    let color = '#0284c7'; // Default detected text
    let fieldTag = '';

    if (matched) {
      fieldTag = matched.field.label;
      const status = evalStatusMap.get(matched.key) || 'PASS';
      if (status === 'FAIL') color = '#ef4444'; // Red
      else if (status === 'WARNING') color = '#f59e0b'; // Amber
      else color = '#10b981'; // Green
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
      color: color
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
      canvasTooltip.innerHTML = `
        <div style="font-weight:600;font-size:0.75rem;color:var(--text-cyan);letter-spacing:0.02em;">${hovered.fieldTag || 'Detected Text Block'}</div>
        <div style="font-size:0.8rem;margin:3px 0;color:var(--text-primary);font-family:var(--font-mono);">"${escapeHtml(hovered.text)}"</div>
        <div style="font-size:0.68rem;color:var(--text-muted);font-family:var(--font-mono);">
          Confidence: ${(hovered.confidence * 100).toFixed(0)}% | Height: ${hovered.height_mm ? `${hovered.height_mm.toFixed(2)} mm` : `${hovered.height} px`}
        </div>
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

async function openMobileConnectModal() {
  const modal = document.getElementById('mobileConnectModal');
  modal.style.display = 'flex';
  document.getElementById('mobileSyncStatus').innerHTML = '<span class="spinner"></span> Generating session...';

  try {
    const res = await fetch('/api/mobile/session', { method: 'POST' });
    const data = await res.json();
    currentMobileSession = data.session_id;

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

    document.getElementById('mobileSyncStatus').innerHTML = '<span class="spinner"></span> Waiting for photo upload from phone...';

    // Start polling for uploaded photo
    startMobilePolling(data.session_id);
  } catch (err) {
    alert('Failed to initialize mobile session: ' + err.message);
  }
}

function closeMobileConnectModal() {
  document.getElementById('mobileConnectModal').style.display = 'none';
  if (mobilePollTimer) {
    clearInterval(mobilePollTimer);
    mobilePollTimer = null;
  }
}

function startMobilePolling(sessionId) {
  if (mobilePollTimer) clearInterval(mobilePollTimer);

  mobilePollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/mobile/poll/${sessionId}`);
      const data = await res.json();

      if (data.status === 'ready') {
        clearInterval(mobilePollTimer);
        mobilePollTimer = null;

        const count = data.filenames ? data.filenames.length : 1;
        document.getElementById('mobileSyncStatus').innerHTML = `<span style="color:var(--text-green);font-weight:600;">Connected:</span> ${count} photo(s) received. Processing on workstation...`;
        setTimeout(() => {
          closeMobileConnectModal();
        }, 800);

        // Load primary image onto canvas and set filenames
        currentFiles = [];
        currentSampleNames = data.filenames || [data.filename];
        document.querySelectorAll('.benchmark-btn').forEach(b => b.classList.remove('active'));

        if (data.image_url) {
          loadImageOntoCanvas(data.image_url);
        }

        // Trigger automatic compliance audit
        setTimeout(() => {
          runAuditWithUploadedFilenames(currentSampleNames);
        }, 400);
      } else if (data.status === 'has_images' || data.uploaded_count > 0) {
        document.getElementById('mobileSyncStatus').innerHTML = `<span class="spinner"></span> Received ${data.uploaded_count} side(s) from phone... Snap more sides or tap 'Send All Sides' on phone!`;
      }
    } catch (e) {
      console.error('Polling error:', e);
    }
  }, 1000);
}

async function runAuditWithUploadedFilenames(filenames) {
  if (!filenames || filenames.length === 0) return;
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

