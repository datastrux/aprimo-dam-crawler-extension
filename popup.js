async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToContent(message) {
  const tab = await getActiveTab();
  if (!tab?.id) throw new Error('No active tab');
  return chrome.tabs.sendMessage(tab.id, message);
}

let lastStats = {};

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
    icon.src = isRunning ? 'images/pause.png' : 'images/play.png';
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

refresh();
setInterval(refresh, 2000);
