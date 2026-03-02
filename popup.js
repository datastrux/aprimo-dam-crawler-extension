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
  document.getElementById('running').textContent = String(!!s.running);
  setCompletionNotice(!!s.completedSuccessfully);
  setCompletionWarningNotice(!!s.completedWithErrors);
  renderRunToggleButton(!!s.running);
}

function renderRunToggleButton(isRunning) {
  const label = document.getElementById('toggleRunLabel');
  const icon = document.getElementById('toggleRunIcon');
  if (label) label.textContent = isRunning ? 'Pause' : 'Start / Resume';
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
  try {
    const res = await sendToContent({ type: 'DAM_CRAWLER_STATUS' });
    if (!res?.ok) {
      setCompletionNotice(false);
      setCompletionWarningNotice(false);
      setStatus(res?.error || 'Not ready on this page');
      return;
    }
    renderStats(res.stats);
    displayStatusText(res.message, res.stats);
  } catch (e) {
    setCompletionNotice(false);
    setCompletionWarningNotice(false);
    setStatus('Open an Aprimo collection or space page and reload it.');
  }
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

function stageLabel(stageName) {
  const cleaned = String(stageName || '').replace(/\.py$/i, '');
  const withoutPrefix = cleaned.replace(/^\d+_/, '');
  return withoutPrefix.replace(/_/g, ' ');
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
    const indicator = stageState === 'completed'
      ? '✓'
      : stageState === 'error'
        ? '!'
        : stageState === 'running'
          ? '⏳'
          : '○';
    const stateText = stageState === 'completed'
      ? 'Completed'
      : stageState === 'error'
        ? (stage?.message || 'Error')
        : stageState === 'running'
          ? 'Running'
          : 'Pending';
    const stateClass = ['running', 'completed', 'error'].includes(stageState) ? stageState : '';
    return `<div class="auditStageRow"><span class="auditStageIndicator">${indicator}</span><span class="auditStageName">${stageLabel(stage?.name)}</span><span class="auditStageState ${stateClass}">${stateText}</span></div>`;
  }).join('');
}

function renderAuditProgress(status = {}) {
  const wrap = document.getElementById('auditProgressWrap');
  const urlText = document.getElementById('auditProgressUrlText');
  const imageText = document.getElementById('auditProgressImageText');
  const fill = document.getElementById('auditProgressFill');
  if (!wrap || !urlText || !imageText || !fill) return;

  const progress = status?.progress;
  const stage = status?.stage || '';
  const isStage01 = stage.includes('01_crawl');
  
  // Only show queue metrics for stage 01
  if (!isStage01) {
    wrap.classList.add('hidden');
    fill.style.width = '0%';
    return;
  }
  
  const current = Number(progress?.current);
  const total = Number(progress?.total);
  const explicitPercent = Number(progress?.percent);
  const hasNumbers = Number.isFinite(current) && Number.isFinite(total) && total > 0;

  if (!hasNumbers) {
    wrap.classList.add('hidden');
    fill.style.width = '0%';
    return;
  }

  const percent = Number.isFinite(explicitPercent)
    ? explicitPercent
    : Math.round((current / total) * 10000) / 100;
  const imagesDiscovered = Number(progress?.images_discovered);
  const imagesPending = Number(progress?.images_pending);
  const hasImageMetrics = Number.isFinite(imagesDiscovered);
  const boundedPercent = Math.max(0, Math.min(100, percent));
  const resumedTag = progress?.resumed ? ' • resumed' : '';
  const message = progress?.message ? ` • ${progress.message}` : '';

  wrap.classList.remove('hidden');
  fill.style.width = `${boundedPercent}%`;
  urlText.textContent = `URLs: ${current.toLocaleString()}/${total.toLocaleString()} (${boundedPercent.toFixed(2)}%)${resumedTag}${message}`;
  imageText.textContent = hasImageMetrics
    ? `Images: ${imagesDiscovered.toLocaleString()} (${Number.isFinite(imagesPending) ? Math.max(0, imagesPending).toLocaleString() : 0} pending)`
    : 'Images: collecting...';
}

async function refreshAuditStatus() {
  try {
    const res = await sendToWorker({ type: 'DAM_AUDIT_STATUS' });
    console.log('[Popup DEBUG] Status response:', JSON.stringify(res, null, 2));
    if (!res?.ok) {
      renderAuditStatus({ state: 'error', message: res?.error || 'Unable to load audit status' });
      renderAuditStages({});
      renderAuditProgress({});
      return;
    }
    if (res.status?.progress) {
      console.log('[Popup DEBUG] Progress data:', JSON.stringify(res.status.progress, null, 2));
    }
    renderAuditStatus(res.status || {});
    renderAuditStages(res.status || {});
    renderAuditProgress(res.status || {});
  } catch (err) {
    renderAuditStatus({ state: 'error', message: String(err?.message || err) });
    renderAuditStages({});
    renderAuditProgress({});
  }
}

async function clickAuditRun() {
  const res = await sendToWorker({ type: 'DAM_AUDIT_START', mode: 'pipeline' });
  if (!res?.ok) {
    setStatus(res?.error || 'Failed to start audit pipeline');
    await refreshAuditStatus();
    return;
  }
  setStatus('Audit pipeline started.');
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
  const res = await sendToWorker({ type: 'DAM_AUDIT_OPEN_OUTPUT' });
  if (!res?.ok) {
    setStatus(res?.error || 'Failed to open output folder');
  }
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

async function clickExportCsv() {
  const res = await sendToContent({ type: 'DAM_CRAWLER_EXPORT_CSV' });
  setStatus(res?.ok ? 'Exported CSV.' : (res?.error || 'Export failed'));
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
document.getElementById('exportCsvBtn').addEventListener('click', () => clickExportCsv().catch(e => setStatus(String(e))));
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
