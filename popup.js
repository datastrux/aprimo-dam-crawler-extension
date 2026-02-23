async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToContent(message) {
  const tab = await getActiveTab();
  if (!tab?.id) throw new Error('No active tab');
  return chrome.tabs.sendMessage(tab.id, message);
}

function setStatus(text) {
  document.getElementById('status').textContent = text;
}

function renderStats(s = {}) {
  document.getElementById('assetCount').textContent = s.assetCount ?? 0;
  document.getElementById('detailDone').textContent = s.detailDone ?? 0;
  document.getElementById('detailErrors').textContent = s.detailErrors ?? 0;
  document.getElementById('running').textContent = String(!!s.running);
}

async function refresh() {
  try {
    const res = await sendToContent({ type: 'DAM_CRAWLER_STATUS' });
    if (!res?.ok) {
      setStatus(res?.error || 'Not ready on this page');
      return;
    }
    setStatus(res.message || 'Ready');
    renderStats(res.stats);
  } catch (e) {
    setStatus('Open an Aprimo collection page and reload it.');
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

async function clickScan() {
  const res = await sendToContent({ type: 'DAM_CRAWLER_SCAN_VISIBLE' });
  setStatus(res?.ok ? `Visible scan added ${res.added} item(s).` : (res?.error || 'Scan failed'));
  await refresh();
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

document.getElementById('startBtn').addEventListener('click', () => clickStart().catch(e => setStatus(String(e))));
document.getElementById('pauseBtn').addEventListener('click', () => clickPause().catch(e => setStatus(String(e))));
document.getElementById('scanBtn').addEventListener('click', () => clickScan().catch(e => setStatus(String(e))));
document.getElementById('exportBtn').addEventListener('click', () => clickExportJson().catch(e => setStatus(String(e))));
document.getElementById('exportCsvBtn').addEventListener('click', () => clickExportCsv().catch(e => setStatus(String(e))));
document.getElementById('resetBtn').addEventListener('click', () => clickReset().catch(e => setStatus(String(e))));

refresh();
setInterval(refresh, 2000);
