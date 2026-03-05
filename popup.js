async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToContent(message) {
  const tab = await getActiveTab();
  if (!tab?.id) throw new Error('No active tab');
  return chrome.tabs.sendMessage(tab.id, message);
}

async function sendToWorker(message) {
  return chrome.runtime.sendMessage(message);
}

let lastStats = {};
const FALLBACK_AUDIT_STAGES = [
  '01_crawl_citizens_images.py',
  '02_build_dam_fingerprints.py',
  '03_build_citizens_fingerprints.py',
  '04_match_assets.py',
  '05_build_reports.py'
];

async function loadTogglePreferences() {
  const checkbox = document.getElementById('downloadPreviews');
  if (!checkbox) return;
  const saved = await chrome.storage.local.get('downloadPreviewsEnabled');
  const hasSaved = typeof saved?.downloadPreviewsEnabled === 'boolean';
  const enabled = hasSaved ? saved.downloadPreviewsEnabled : true;
  checkbox.checked = enabled;
  if (!hasSaved) {
    await chrome.storage.local.set({ downloadPreviewsEnabled: true });
  }
}

async function saveTogglePreferences() {
  const checkbox = document.getElementById('downloadPreviews');
  if (!checkbox) return;
  await chrome.storage.local.set({ downloadPreviewsEnabled: !!checkbox.checked });
}

function setStatus(text) {
  document.getElementById('status').textContent = text;
}

function setCompletionNotice(visible) {
  const el = document.getElementById('completionNotice');
  if (!el) return;
  el.classList.toggle('hidden', !visible);
}

function setCompletionWarningNotice(visible) {
  const el = document.getElementById('completionWarningNotice');
  if (!el) return;
  el.classList.toggle('hidden', !visible);
}

function renderStats(s = {}) {
  lastStats = s || {};
  document.getElementById('assetCount').textContent = s.assetCount ?? 0;
  document.getElementById('detailDone').textContent = s.detailDone ?? 0;
  document.getElementById('detailErrors').textContent = s.detailErrors ?? 0;
  
  const runningEl = document.getElementById('running');
  const damPhaseStatus = document.getElementById('damPhaseStatus');
  
  if (s.running) {
    runningEl.textContent = 'Active';
    runningEl.style.color = '#0969da';
    runningEl.style.fontWeight = '600';
    if (damPhaseStatus) {
      damPhaseStatus.textContent = 'Collecting';
      damPhaseStatus.classList.add('active');
      damPhaseStatus.classList.remove('success', 'error');
    }
  } else if (s.completedSuccessfully) {
    runningEl.textContent = 'Complete';
    runningEl.style.color = '#116329';
    runningEl.style.fontWeight = '600';
    if (damPhaseStatus) {
      damPhaseStatus.textContent = 'Complete';
      damPhaseStatus.classList.add('success');
      damPhaseStatus.classList.remove('active', 'error');
    }
  } else if (s.completedWithErrors) {
    runningEl.textContent = 'Error';
    runningEl.style.color = '#d1242f';
    runningEl.style.fontWeight = '600';
    if (damPhaseStatus) {
      damPhaseStatus.textContent = 'Has Errors';
      damPhaseStatus.classList.add('error');
      damPhaseStatus.classList.remove('active', 'success');
    }
  } else {
    runningEl.textContent = 'Idle';
    runningEl.style.color = '#57606a';
    runningEl.style.fontWeight = '400';
    if (damPhaseStatus) {
      damPhaseStatus.textContent = 'Idle';
      damPhaseStatus.classList.remove('active', 'success', 'error');
    }
  }
  
  setCompletionNotice(!!s.completedSuccessfully);
  setCompletionWarningNotice(!!s.completedWithErrors);
  renderRunToggleButton(!!s.running);
}

function renderRunToggleButton(isRunning) {
  const label = document.getElementById('toggleRunLabel');
  const icon = document.getElementById('toggleRunIcon');
  if (label) label.textContent = isRunning ? 'Pause Collection' : 'Start Collection';
  if (icon) {
    icon.src = isRunning ? 'assets/images/pause.png' : 'assets/images/play.png';
    icon.alt = isRunning ? 'Pause' : 'Start';
  }
}

function displayStatusText(message, stats = {}) {
  if (stats?.completedSuccessfully || stats?.completedWithErrors) {
    setStatus('Ready');
    return;
  }
  setStatus(message || 'Ready');
}

async function refresh() {
  // Always try to get current crawl state first
  try {
    const res = await sendToContent({ type: 'DAM_CRAWLER_STATUS' });
    if (res?.ok) {
      // We have active state - show it
      renderStats(res.stats);
      displayStatusText(res.message, res.stats);
      return;
    }
  } catch (e) {
    // Content script not available or no active state
    console.log('[Refresh] No active crawl state:', e);
  }
  
  // No active crawl - check if Phase 1 was previously completed
  const damAssets = await checkDamAssetsExist();
  
  if (damAssets.exists) {
    // Phase 1 is complete - show as done with asset count
    setStatus(`Master catalog: ${damAssets.count.toLocaleString()} assets. Re-crawl DAM to add more.`);
    renderPhase1Complete(damAssets.count);
    return;
  }
  
  // No active crawl and no dam_assets.json - show instructions
  setCompletionNotice(false);
  setCompletionWarningNotice(false);
  setStatus('Open an Aprimo collection or space page and reload it.');
}

async function checkDamAssetsExist() {
  try {
    const url = chrome.runtime.getURL('assets/audit/dam_assets.json');
    const response = await fetch(url);
    if (!response.ok) return { exists: false, count: 0 };
    
    // Verify it's valid JSON with assets
    const data = await response.json();
    const count = Array.isArray(data) ? data.length : 0;
    return { exists: count > 0, count };
  } catch (err) {
    console.log('[Phase 1 Check] dam_assets.json not found or invalid:', err);
    return { exists: false, count: 0 };
  }
}

function renderPhase1Complete(assetCount = 0) {
  // Update Phase 1 status
  const damPhaseStatus = document.getElementById('damPhaseStatus');
  if (damPhaseStatus) {
    damPhaseStatus.textContent = 'Complete ✓';
    damPhaseStatus.classList.add('success');
    damPhaseStatus.classList.remove('active', 'error');
  }
  
  // Show existing asset count from master catalog
  if (assetCount > 0) {
    renderStats({
      assetCount: assetCount,
      detailDone: assetCount,
      detailErrors: 0,
      running: false,
      completedSuccessfully: true
    });
  }
  
  // Keep stats visible but update status text to show completion
  const statsEl = document.querySelector('.section .stats');
  if (statsEl) {
    statsEl.style.display = 'grid';
  }
  
  // Keep all Phase 1 action buttons visible
  // User can re-crawl DAM, export/import, or reset as needed
  const phase1Section = document.querySelector('.section');
  if (phase1Section) {
    const phase1Actions = phase1Section.querySelectorAll('.actionGrid');
    // Show all action grids
    phase1Actions.forEach(grid => {
      grid.style.display = 'grid';
    });
  }
  
  // Keep checkbox visible for re-crawls
  const checkbox = document.querySelector('.checkboxRow');
  if (checkbox) {
    checkbox.style.display = 'flex';
  }
  
  setCompletionNotice(false);
  setCompletionWarningNotice(false);
}

function renderAuditStatus(status = {}) {
  const el = document.getElementById('auditStatus');
  if (!el) return;
  
  const state = status?.state || 'idle';
  const isRunning = (state === 'running') || (status?.running === true);
  const progress = status?.progress;
  const heartbeat = status?.heartbeat;
  const reconnect = status?.reconnect;
  
  // Clear existing content
  el.textContent = '';
  
  // Show reconnecting state
  if (state === 'reconnecting') {
    const attempts = reconnect?.attempts || 0;
    const maxAttempts = reconnect?.maxAttempts || 10;
    const span = document.createElement('span');
    span.style.color = 'orange';
    span.textContent = `Audit: reconnecting (attempt ${attempts}/${maxAttempts})`;
    el.appendChild(span);
    return;
  }
  
  // Build status text safely
  let statusText = '';
  
  if (isRunning && progress) {
    const current = Number(progress.current);
    const total = Number(progress.total);
    const percent = Number(progress.percent);
    const imagesDiscovered = Number(progress.images_discovered);
    const imagesPending = Number(progress.images_pending);
    
    statusText = 'Audit: running';
    if (status.stage) {
      statusText += ` (${status.stage})`;
    }
    
    if (Number.isFinite(current) && Number.isFinite(total)) {
      statusText += `\nURLs: ${current.toLocaleString()}/${total.toLocaleString()} (${percent.toFixed(1)}%)`;
    }
    
    if (Number.isFinite(imagesDiscovered)) {
      statusText += `\nImages: ${imagesDiscovered.toLocaleString()} discovered`;
      if (Number.isFinite(imagesPending)) {
        statusText += ` (${imagesPending.toLocaleString()} pending)`;
      }
    }
    
    // Add stale warning if needed
    if (heartbeat?.stale) {
      statusText += '\n⚠ No response (may be hung)';
    }
  } else {
    const stage = status?.stage ? ` (${status.stage})` : '';
    const msg = status?.message ? ` - ${status.message}` : '';
    statusText = `Audit: ${state}${stage}${msg}`;
    
    if (heartbeat?.stale && isRunning) {
      statusText += '\n⚠ No response (may be hung)';
    }
  }
  
  // Set text content safely (no HTML injection possible)
  el.style.whiteSpace = 'pre-line';
  el.textContent = statusText;
}

const PHASE_METADATA = {
  '01_crawl_citizens_images': {
    number: 2,
    title: 'Collection Crawl',
    description: 'Discover and collect Citizens Bank image URLs'
  },
  '02_build_dam_fingerprints': {
    number: 3,
    title: 'DAM Fingerprints',
    description: 'Generate perceptual hashes for DAM assets'
  },
  '03_build_citizens_fingerprints': {
    number: 4,
    title: 'Web Fingerprints',
    description: 'Generate perceptual hashes for web images'
  },
  '04_match_assets': {
    number: 5,
    title: 'Asset Matching',
    description: 'Match DAM assets to web images'
  },
  '05_build_reports': {
    number: 6,
    title: 'Report Generation',
    description: 'Create comprehensive audit reports'
  }
};

function getPhaseMetadata(stageName) {
  const cleaned = String(stageName || '').replace(/\.py$/i, '');
  const key = cleaned.replace(/^\d+_/, '');
  
  // Try direct match first
  for (const [phaseKey, metadata] of Object.entries(PHASE_METADATA)) {
    if (phaseKey.includes(key) || key.includes(phaseKey.replace(/^\d+_/, ''))) {
      return metadata;
    }
  }
  
  // Fallback
  const withoutPrefix = cleaned.replace(/^\d+_/, '');
  const title = withoutPrefix.replace(/_/g, ' ');
  return { number: '?', title, description: '' };
}

function stageLabel(stageName) {
  const metadata = getPhaseMetadata(stageName);
  return metadata.title;
}

function renderAuditStages(status = {}) {
  const container = document.getElementById('auditStages');
  if (!container) return;

  const provided = Array.isArray(status?.stages) ? status.stages : [];
  const stages = provided.length
    ? provided
    : FALLBACK_AUDIT_STAGES.map((name) => ({ name, status: 'pending', message: null }));

  container.innerHTML = stages.map((stage) => {
    const stageState = stage?.status || 'pending';
    const metadata = getPhaseMetadata(stage?.name);
    
    const indicator = stageState === 'completed'
      ? '✓'
      : stageState === 'error'
        ? '✗'
        : stageState === 'running'
          ? '▶'
          : metadata.number;
    
    const badgeText = stageState === 'completed'
      ? 'Done'
      : stageState === 'error'
        ? 'Error'
        : stageState === 'running'
          ? 'Active'
          : 'Pending';
    
    const cardClass = ['running', 'completed', 'error'].includes(stageState) ? stageState : '';
    
    return `
      <div class="phaseCard ${cardClass}">
        <div class="phaseIndicator">${indicator}</div>
        <div class="phaseInfo">
          <div class="phaseName">${metadata.title}</div>
          <div class="phaseDescription">${metadata.description || ''}</div>
        </div>
        <div class="phaseBadge">${badgeText}</div>
      </div>
    `;
  }).join('');
}

function renderAuditProgress(status = {}) {
  const wrap = document.getElementById('auditProgressWrap');
  const phaseLabel = document.getElementById('auditProgressPhaseLabel');
  const percentLabel = document.getElementById('auditProgressPercent');
  const urlText = document.getElementById('auditProgressUrlText');
  const imageText = document.getElementById('auditProgressImageText');
  const fill = document.getElementById('auditProgressFill');
  if (!wrap || !phaseLabel || !percentLabel || !urlText || !imageText || !fill) return;

  const progress = status?.progress;
  const stage = status?.stage || '';
  const isStage01 = stage.includes('01_crawl');
  const isRunning = status?.state === 'running' || status?.running;
  
  // Only show progress bar for stage 01 or when running
  if (!isStage01 && !isRunning) {
    wrap.classList.add('hidden');
    fill.style.width = '0%';
    return;
  }
  
  const current = Number(progress?.current);
  const total = Number(progress?.total);
  const explicitPercent = Number(progress?.percent);
  const hasNumbers = Number.isFinite(current) && Number.isFinite(total) && total > 0;

  if (!hasNumbers && isStage01) {
    wrap.classList.add('hidden');
    fill.style.width = '0%';
    return;
  }

  const percent = Number.isFinite(explicitPercent)
    ? explicitPercent
    : hasNumbers ? Math.round((current / total) * 10000) / 100 : 0;
  const imagesDiscovered = Number(progress?.images_discovered);
  const imagesPending = Number(progress?.images_pending);
  const hasImageMetrics = Number.isFinite(imagesDiscovered);
  const boundedPercent = Math.max(0, Math.min(100, percent));
  const metadata = getPhaseMetadata(stage);

  wrap.classList.remove('hidden');
  fill.style.width = `${boundedPercent}%`;
  phaseLabel.textContent = `Phase ${metadata.number}: ${metadata.title}`;
  percentLabel.textContent = `${boundedPercent.toFixed(1)}%`;
  
  if (hasNumbers) {
    urlText.textContent = `URLs Processed: ${current.toLocaleString()} of ${total.toLocaleString()}`;
  } else {
    urlText.textContent = 'Processing...';
  }
  
  if (hasImageMetrics) {
    const pendingCount = Number.isFinite(imagesPending) ? Math.max(0, imagesPending) : 0;
    imageText.textContent = `Images: ${imagesDiscovered.toLocaleString()} discovered, ${pendingCount.toLocaleString()} pending`;
  } else {
    imageText.textContent = 'Discovering images...';
  }
}

async function refreshAuditStatus() {
  try {
    const res = await sendToWorker({ type: 'DAM_AUDIT_STATUS' });
    console.log('[Popup DEBUG] Status response:', JSON.stringify(res, null, 2));
    if (!res?.ok) {
      renderAuditStatus({ state: 'error', message: res?.error || 'Unable to load audit status' });
      renderAuditStages({});
      renderAuditProgress({});
      updatePipelinePhaseStatus({ state: 'error' });
      return;
    }
    if (res.status?.progress) {
      console.log('[Popup DEBUG] Progress data:', JSON.stringify(res.status.progress, null, 2));
    }
    renderAuditStatus(res.status || {});
    renderAuditStages(res.status || {});
    renderAuditProgress(res.status || {});
    updatePipelinePhaseStatus(res.status || {});
  } catch (err) {
    renderAuditStatus({ state: 'error', message: String(err?.message || err) });
    renderAuditStages({});
    renderAuditProgress({});
    updatePipelinePhaseStatus({ state: 'error' });
  }
}

function updatePipelinePhaseStatus(status) {
  const pipelineStatus = document.getElementById('pipelinePhaseStatus');
  if (!pipelineStatus) return;
  
  const state = status?.state || 'idle';
  const isRunning = state === 'running' || status?.running;
  
  if (isRunning) {
    pipelineStatus.textContent = 'Running';
    pipelineStatus.classList.add('active');
    pipelineStatus.classList.remove('success', 'error');
  } else if (state === 'completed') {
    pipelineStatus.textContent = 'Complete';
    pipelineStatus.classList.add('success');
    pipelineStatus.classList.remove('active', 'error');
  } else if (state === 'error') {
    pipelineStatus.textContent = 'Error';
    pipelineStatus.classList.add('error');
    pipelineStatus.classList.remove('active', 'success');
  } else {
    pipelineStatus.textContent = 'Idle';
    pipelineStatus.classList.remove('active', 'success', 'error');
  }
}

async function clickAuditRun() {
  // Get threshold value from UI
  const thresholdInput = document.getElementById('phashThreshold');
  const threshold = thresholdInput ? parseInt(thresholdInput.value, 10) : 8;
  
  // Validate threshold
  if (isNaN(threshold) || threshold < 0 || threshold > 20) {
    setStatus('Invalid threshold value. Must be between 0 and 20.');
    return;
  }
  
  const res = await sendToWorker({ 
    type: 'DAM_AUDIT_START', 
    mode: 'pipeline',
    phashThreshold: threshold
  });
  if (!res?.ok) {
    setStatus(res?.error || 'Failed to start audit pipeline');
    await refreshAuditStatus();
    return;
  }
  setStatus(`Audit pipeline started (threshold: ${threshold}).`);
  await refreshAuditStatus();
}

async function clickAuditStop() {
  const res = await sendToWorker({ type: 'DAM_AUDIT_STOP' });
  if (!res?.ok) {
    setStatus(res?.error || 'Failed to stop audit pipeline');
    await refreshAuditStatus();
    return;
  }
  setStatus('Audit stop requested.');
  await refreshAuditStatus();
}

async function clickOpenOutputFolder() {
  // Open the HTML report directly in a new tab
  chrome.tabs.create({
    url: chrome.runtime.getURL('reports/audit_report.html')
  });
}

async function clickStart() {
  const downloadPreviews = document.getElementById('downloadPreviews').checked;
  setStatus('Starting…');
  const res = await sendToContent({ type: 'DAM_CRAWLER_START', options: { downloadPreviews } });
  if (!res?.ok) setStatus(res?.error || 'Start failed');
  await refresh();
}

async function clickPause() {
  const res = await sendToContent({ type: 'DAM_CRAWLER_PAUSE' });
  setStatus(res?.ok ? 'Paused.' : (res?.error || 'Pause failed'));
  await refresh();
}

async function clickToggleRun() {
  if (lastStats?.running) {
    await clickPause();
    return;
  }
  await clickStart();
}

async function clickScan() {
  const res = await sendToContent({ type: 'DAM_CRAWLER_SCAN_VISIBLE' });
  setStatus(res?.ok ? `Visible scan added ${res.added} item(s).` : (res?.error || 'Scan failed'));
  await refresh();
}

async function clickRecheckIncomplete() {
  const downloadPreviews = document.getElementById('downloadPreviews').checked;
  setStatus('Rechecking incomplete details…');
  const res = await sendToContent({ type: 'DAM_CRAWLER_RECHECK_INCOMPLETE', options: { downloadPreviews } });
  if (!res?.ok) {
    setStatus(res?.error || 'Recheck failed');
    return;
  }
  setStatus(`Recheck finished. Processed ${res.processed ?? 0} incomplete item(s).`);
  await refresh();
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('File read failed'));
    reader.readAsText(file);
  });
}

async function clickImportJson() {
  const input = document.getElementById('importFileInput');
  input.value = '';
  input.click();
}

async function handleImportFileChange(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  try {
    setStatus('Importing JSON…');
    const text = await readFileAsText(file);
    const payload = JSON.parse(text);
    const res = await sendToContent({ type: 'DAM_CRAWLER_IMPORT_STATE', payload });
    if (!res?.ok) {
      setStatus(res?.error || 'Import failed');
      return;
    }
    setStatus(`Import complete. Added ${res.added ?? 0}, updated ${res.updated ?? 0}, skipped ${res.skipped ?? 0}.`);
    await refresh();
  } catch (err) {
    setStatus(`Import failed: ${String(err?.message || err)}`);
  }
}

async function clickExportJson() {
  const res = await sendToContent({ type: 'DAM_CRAWLER_EXPORT_JSON' });
  setStatus(res?.ok ? 'Exported JSON.' : (res?.error || 'Export failed'));
}

async function clickReset() {
  const res = await sendToContent({ type: 'DAM_CRAWLER_RESET' });
  setStatus(res?.ok ? 'State reset.' : (res?.error || 'Reset failed'));
  await refresh();
}

document.getElementById('toggleRunBtn').addEventListener('click', () => clickToggleRun().catch(e => setStatus(String(e))));
document.getElementById('scanBtn').addEventListener('click', () => clickScan().catch(e => setStatus(String(e))));
document.getElementById('recheckBtn').addEventListener('click', () => clickRecheckIncomplete().catch(e => setStatus(String(e))));
document.getElementById('exportBtn').addEventListener('click', () => clickExportJson().catch(e => setStatus(String(e))));
document.getElementById('importBtn').addEventListener('click', () => clickImportJson().catch(e => setStatus(String(e))));
document.getElementById('importFileInput').addEventListener('change', (e) => handleImportFileChange(e).catch(err => setStatus(String(err))));
document.getElementById('resetBtn').addEventListener('click', () => clickReset().catch(e => setStatus(String(e))));
document.getElementById('auditRunBtn').addEventListener('click', () => clickAuditRun().catch(e => setStatus(String(e))));
document.getElementById('auditStopBtn').addEventListener('click', () => clickAuditStop().catch(e => setStatus(String(e))));

const openOutputBtn = document.getElementById('auditOpenOutputBtn');
if (openOutputBtn) {
  openOutputBtn.addEventListener('click', () => clickOpenOutputFolder().catch(e => setStatus(String(e))));
}

refresh();
setInterval(refresh, 2000);
refreshAuditStatus();
setInterval(refreshAuditStatus, 500);  // Poll every 500ms for responsive audit progress
loadTogglePreferences().catch(() => {});
document.getElementById('downloadPreviews').addEventListener('change', () => {
  saveTogglePreferences().catch(() => {});
});
