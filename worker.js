// Background worker for downloads and native-host audit orchestration.

const AUDIT_NATIVE_HOST = 'com.datastrux.dam_audit_host';
const AUDIT_STAGES = [
  '01_crawl_citizens_images.py',
  '02_build_dam_fingerprints.py',
  '03_build_citizens_fingerprints.py',
  '04_match_assets.py',
  '05_build_reports.py'
];

function createStageStates() {
  return AUDIT_STAGES.map((name) => ({
    name,
    status: 'pending',
    message: null
  }));
}

const auditRuntime = {
  running: false,
  state: 'idle',
  startedAt: null,
  finishedAt: null,
  stage: null,
  message: null,
  progress: null,
  stages: createStageStates(),
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
  auditRuntime.progress = null;
  auditRuntime.stages = createStageStates();
  auditRuntime.error = null;
  auditRuntime.result = null;
  auditRuntime.logs = [];
}

function updateStage(stageName, patch) {
  if (!stageName) return;
  const target = auditRuntime.stages.find((s) => s.name === stageName);
  if (!target) return;
  Object.assign(target, patch);
}

function markRunningStage(stageName) {
  for (const stage of auditRuntime.stages) {
    if (stage.name === stageName) {
      stage.status = 'running';
      stage.message = null;
      continue;
    }
    if (stage.status === 'running') {
      stage.status = 'pending';
      stage.message = null;
    }
  }
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
    progress: auditRuntime.progress,
    stages: auditRuntime.stages,
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
    if (msg.stage && msg.status === 'running') {
      markRunningStage(msg.stage);
    }
    if (msg.message) pushAuditLog(msg.message);
    return;
  }
  if (type === 'log') {
    if (msg.message) pushAuditLog(msg.message);
    return;
  }
  if (type === 'progress') {
    const current = Number(msg.current);
    const total = Number(msg.total);
    const explicitPercent = Number(msg.percent);
    const imagesDiscovered = Number(msg.images_discovered);
    const imagesPending = Number(msg.images_pending);
    const percent = Number.isFinite(explicitPercent)
      ? explicitPercent
      : (Number.isFinite(current) && Number.isFinite(total) && total > 0 ? Math.round((current / total) * 10000) / 100 : 0);

    auditRuntime.stage = msg.stage || auditRuntime.stage;
    auditRuntime.progress = {
      current: Number.isFinite(current) ? current : 0,
      total: Number.isFinite(total) ? total : 0,
      percent,
      message: msg.message || null,
      resumed: !!msg.resumed,
      images_discovered: Number.isFinite(imagesDiscovered) ? imagesDiscovered : 0,
      images_pending: Number.isFinite(imagesPending) ? imagesPending : 0
    };
    if (msg.message) {
      auditRuntime.message = msg.message;
    }
    return;
  }
  if (type === 'stage_start') {
    auditRuntime.stage = msg.stage || auditRuntime.stage;
    markRunningStage(msg.stage);
    return;
  }
  if (type === 'stage_complete') {
    updateStage(msg.stage, { status: 'completed', message: 'Completed' });
    return;
  }
  if (type === 'complete') {
    auditRuntime.running = false;
    auditRuntime.state = 'completed';
    auditRuntime.finishedAt = new Date().toISOString();
    auditRuntime.result = msg.result || null;
    auditRuntime.message = msg.message || 'Audit pipeline completed';
    for (const stage of auditRuntime.stages) {
      if (stage.status === 'running') {
        stage.status = 'completed';
        stage.message = stage.message || 'Completed';
      }
    }
    pushAuditLog(auditRuntime.message);
    return;
  }
  if (type === 'error') {
    auditRuntime.running = false;
    auditRuntime.state = 'error';
    auditRuntime.finishedAt = new Date().toISOString();
    auditRuntime.error = msg.error || 'Unknown native host error';
    auditRuntime.message = auditRuntime.error;
    if (msg.stage) {
      updateStage(msg.stage, { status: 'error', message: msg.error || 'Stage failed' });
    } else if (auditRuntime.stage) {
      updateStage(auditRuntime.stage, { status: 'error', message: msg.error || 'Stage failed' });
    }
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
