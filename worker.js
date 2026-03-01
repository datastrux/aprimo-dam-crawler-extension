// Background worker for downloads and native-host audit orchestration.

const AUDIT_NATIVE_HOST = 'com.datastrux.dam_audit_host';

const auditRuntime = {
  running: false,
  state: 'idle',
  startedAt: null,
  finishedAt: null,
  stage: null,
  message: null,
  error: null,
  result: null,
  logs: []
};

let auditPort = null;

function resetAuditRuntime() {
  auditRuntime.running = false;
  auditRuntime.state = 'idle';
  auditRuntime.startedAt = null;
  auditRuntime.finishedAt = null;
  auditRuntime.stage = null;
  auditRuntime.message = null;
  auditRuntime.error = null;
  auditRuntime.result = null;
  auditRuntime.logs = [];
}

function pushAuditLog(message) {
  if (!message) return;
  auditRuntime.logs.push({ at: new Date().toISOString(), message: String(message) });
  if (auditRuntime.logs.length > 250) {
    auditRuntime.logs = auditRuntime.logs.slice(auditRuntime.logs.length - 250);
  }
}

function getAuditStatusPayload() {
  return {
    running: auditRuntime.running,
    state: auditRuntime.state,
    startedAt: auditRuntime.startedAt,
    finishedAt: auditRuntime.finishedAt,
    stage: auditRuntime.stage,
    message: auditRuntime.message,
    error: auditRuntime.error,
    result: auditRuntime.result,
    logs: auditRuntime.logs
  };
}

function handleAuditHostMessage(msg) {
  const type = msg?.type;
  if (type === 'status') {
    auditRuntime.state = msg.status || auditRuntime.state;
    auditRuntime.stage = msg.stage || auditRuntime.stage;
    auditRuntime.message = msg.message || auditRuntime.message;
    if (msg.message) pushAuditLog(msg.message);
    return;
  }
  if (type === 'log') {
    if (msg.message) pushAuditLog(msg.message);
    return;
  }
  if (type === 'complete') {
    auditRuntime.running = false;
    auditRuntime.state = 'completed';
    auditRuntime.finishedAt = new Date().toISOString();
    auditRuntime.result = msg.result || null;
    auditRuntime.message = msg.message || 'Audit pipeline completed';
    pushAuditLog(auditRuntime.message);
    return;
  }
  if (type === 'error') {
    auditRuntime.running = false;
    auditRuntime.state = 'error';
    auditRuntime.finishedAt = new Date().toISOString();
    auditRuntime.error = msg.error || 'Unknown native host error';
    auditRuntime.message = auditRuntime.error;
    pushAuditLog(`ERROR: ${auditRuntime.error}`);
  }
}

function startAuditNativeRun(mode, stage) {
  if (auditRuntime.running) {
    return { ok: false, error: 'Audit already running' };
  }

  resetAuditRuntime();
  auditRuntime.running = true;
  auditRuntime.state = 'starting';
  auditRuntime.startedAt = new Date().toISOString();

  try {
    auditPort = chrome.runtime.connectNative(AUDIT_NATIVE_HOST);
  } catch (err) {
    auditRuntime.running = false;
    auditRuntime.state = 'error';
    auditRuntime.error = String(err?.message || err);
    return { ok: false, error: auditRuntime.error };
  }

  auditPort.onMessage.addListener(handleAuditHostMessage);
  auditPort.onDisconnect.addListener(() => {
    if (auditRuntime.running) {
      const runtimeErr = chrome.runtime.lastError?.message;
      auditRuntime.running = false;
      auditRuntime.state = 'error';
      auditRuntime.finishedAt = new Date().toISOString();
      auditRuntime.error = runtimeErr || auditRuntime.error || 'Native host disconnected unexpectedly';
      auditRuntime.message = auditRuntime.error;
      pushAuditLog(`ERROR: ${auditRuntime.error}`);
    }
    auditPort = null;
  });

  auditPort.postMessage({ command: 'run', mode, stage });
  pushAuditLog(`Started audit run mode=${mode}${stage ? ` stage=${stage}` : ''}`);

  return { ok: true, started: true };
}

function stopAuditNativeRun() {
  if (!auditPort || !auditRuntime.running) {
    return { ok: false, error: 'No running audit to stop' };
  }
  try {
    auditPort.postMessage({ command: 'stop' });
    auditRuntime.state = 'stopping';
    auditRuntime.message = 'Stop requested';
    pushAuditLog('Stop requested');
    return { ok: true, stopping: true };
  } catch (err) {
    return { ok: false, error: String(err?.message || err) };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg?.type === 'DAM_CRAWLER_DOWNLOAD_BLOB') {
        const { blobUrl, filename } = msg;
        const downloadId = await chrome.downloads.download({ url: blobUrl, filename, saveAs: false, conflictAction: 'uniquify' });
        sendResponse({ ok: true, downloadId });
        return;
      }

      if (msg?.type === 'DAM_CRAWLER_DOWNLOAD_URL') {
        const { url, filename, overwrite } = msg;
        const downloadId = await chrome.downloads.download({ url, filename, saveAs: false, conflictAction: overwrite ? 'overwrite' : 'uniquify' });
        sendResponse({ ok: true, downloadId });
        return;
      }

      if (msg?.type === 'DAM_AUDIT_START') {
        const mode = msg?.mode || 'pipeline';
        const stage = msg?.stage || null;
        sendResponse(startAuditNativeRun(mode, stage));
        return;
      }

      if (msg?.type === 'DAM_AUDIT_STOP') {
        sendResponse(stopAuditNativeRun());
        return;
      }

      if (msg?.type === 'DAM_AUDIT_STATUS') {
        sendResponse({ ok: true, status: getAuditStatusPayload() });
        return;
      }

      if (msg?.type === 'DAM_AUDIT_CLEAR_LOGS') {
        auditRuntime.logs = [];
        sendResponse({ ok: true });
        return;
      }

      sendResponse({ ok: false, error: 'Unknown message type' });
    } catch (err) {
      sendResponse({ ok: false, error: String(err?.message || err) });
    }
  })();
  return true;
});
