// Background worker for downloads and native-host audit orchestration.

import { encryptedStorage } from './encrypted_storage.js';

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
  state: 'idle',  // idle | starting | running | reconnecting | stopping | completed | error
  startedAt: null,
  finishedAt: null,
  stage: null,
  message: null,
  progress: null,
  stages: createStageStates(),
  error: null,
  result: null,
  logs: [],
  runId: null,
  lastHeartbeatAt: null,
  reconnectAttempts: 0,
  maxReconnectAttempts: 10
};

let auditPort = null;
let heartbeatInterval = null;
const HEARTBEAT_INTERVAL_MS = 2000;  // 2 seconds
const STALE_THRESHOLD_MS = 10000;    // 10 seconds (5 missed heartbeats)
const MAX_GLOBAL_TIMEOUT_MS = 300000; // 5 minutes
const STORAGE_KEY = 'auditRuntime';
const MAX_RECONNECT_ATTEMPTS = 10;

// HMAC signature verification
let auditSecretKey = null;

// Load secret key from encrypted storage on startup
(async () => {
  try {
    const result = await encryptedStorage.get(['auditSecretKey']);
    if (result.auditSecretKey) {
      auditSecretKey = result.auditSecretKey;
      console.log('[Worker] HMAC secret loaded from encrypted storage');
    } else {
      console.warn('[Worker] No HMAC secret found. Run: python scripts/generate_audit_secret.py');
    }
  } catch (err) {
    console.error('[Worker] Failed to load HMAC secret:', err);
  }
})();

/**
 * Sign command with HMAC-SHA256 signature
 * @param {Object} command - Command object to sign
 * @returns {Promise<Object>} Command with signature field added
 */
async function signCommand(command) {
  if (!auditSecretKey) {
    // No secret configured, send unsigned (backward compatibility)
    console.warn('[Worker] Sending unsigned command (no secret key)');
    return command;
  }

  // Create canonical representation (sorted keys)
  const canonical = JSON.stringify(command, Object.keys(command).sort());
  const encoder = new TextEncoder();
  const data = encoder.encode(canonical);
  
  // Convert hex secret to ArrayBuffer
  const keyData = new Uint8Array(auditSecretKey.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
  
  // Import key for HMAC
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  
  // Generate signature
  const signature = await crypto.subtle.sign('HMAC', cryptoKey, data);
  const hashArray = Array.from(new Uint8Array(signature));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  
  // Add signature to command
  return { ...command, signature: hashHex };
}

/**
 * Send signed command to native host
 * @param {Object} command - Command to send
 */
async function sendSignedCommand(command) {
  if (!auditPort) {
    console.error('[Worker] Cannot send command: no active port');
    return;
  }
  
  try {
    const signedCommand = await signCommand(command);
    auditPort.postMessage(signedCommand);
  } catch (err) {
    console.error('[Worker] Failed to sign command:', err);
    throw err;
  }
}

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
  auditRuntime.runId = null;
  auditRuntime.lastHeartbeatAt = null;
  auditRuntime.reconnectAttempts = 0;
  stopHeartbeat();
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatInterval = setInterval(() => {
    if (auditPort && auditRuntime.running) {
      try {
        sendSignedCommand({ command: 'status' });
      } catch (err) {
        console.warn('[Worker] Heartbeat failed:', err);
      }
    }
  }, HEARTBEAT_INTERVAL_MS);
}

async function persistRuntime() {
  try {
    await chrome.storage.local.set({ [STORAGE_KEY]: auditRuntime });
  } catch (err) {
    console.warn('[Worker] Failed to persist runtime:', err);
  }
}

async function restoreRuntime() {
  try {
    const stored = await chrome.storage.local.get(STORAGE_KEY);
    if (stored?.[STORAGE_KEY]) {
      Object.assign(auditRuntime, stored[STORAGE_KEY]);
      console.log('[Worker] Restored runtime from storage');
      // If was running, attempt reconnect
      if (auditRuntime.running && auditRuntime.state === 'running') {
        attemptReconnect();
      }
    }
  } catch (err) {
    console.warn('[Worker] Failed to restore runtime:', err);
  }
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
  const now = Date.now();
  const stale = auditRuntime.lastHeartbeatAt && (now - auditRuntime.lastHeartbeatAt > STALE_THRESHOLD_MS);
  
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
    logs: auditRuntime.logs,
    runId: auditRuntime.runId,
    heartbeat: {
      lastSeenAt: auditRuntime.lastHeartbeatAt,
      stale: stale,
      staleThresholdMs: STALE_THRESHOLD_MS
    },
    reconnect: {
      attempts: auditRuntime.reconnectAttempts,
      maxAttempts: auditRuntime.maxReconnectAttempts
    }
  };
}

function handleAuditHostMessage(msg) {
  const type = msg?.type;
  
  // Update heartbeat timestamp on any message
  auditRuntime.lastHeartbeatAt = Date.now();
  
  // Capture runId if present
  if (msg?.runId && !auditRuntime.runId) {
    auditRuntime.runId = msg.runId;
  }
  
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
    console.log('[Worker DEBUG] Progress message received:', JSON.stringify(msg, null, 2));
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
    console.log('[Worker DEBUG] Updated auditRuntime.progress:', JSON.stringify(auditRuntime.progress, null, 2));
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
    stopHeartbeat();
    persistRuntime();
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
    stopHeartbeat();
    persistRuntime();
  }
}

function attemptReconnect() {
  // Check global timeout (5 minutes since start)
  if (auditRuntime.startedAt) {
    const elapsed = Date.now() - new Date(auditRuntime.startedAt).getTime();
    if (elapsed > MAX_GLOBAL_TIMEOUT_MS) {
      auditRuntime.running = false;
      auditRuntime.state = 'error';
      auditRuntime.error = 'Reconnect timeout: 5 minutes elapsed';
      auditRuntime.message = auditRuntime.error;
      pushAuditLog(`ERROR: ${auditRuntime.error}`);
      stopHeartbeat();
      persistRuntime();
      return;
    }
  }

  if (auditRuntime.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    auditRuntime.running = false;
    auditRuntime.state = 'error';
    auditRuntime.error = `Failed to reconnect after ${MAX_RECONNECT_ATTEMPTS} attempts`;
    auditRuntime.message = auditRuntime.error;
    pushAuditLog(`ERROR: ${auditRuntime.error}`);
    stopHeartbeat();
    persistRuntime();
    return;
  }

  auditRuntime.state = 'reconnecting';
  auditRuntime.reconnectAttempts++;
  auditRuntime.message = `Reconnecting (attempt ${auditRuntime.reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`;
  pushAuditLog(auditRuntime.message);
  persistRuntime();

  const delay = Math.min(1000 * Math.pow(2, auditRuntime.reconnectAttempts - 1), 30000);
  
  setTimeout(() => {
    try {
      auditPort = chrome.runtime.connectNative(AUDIT_NATIVE_HOST);
      auditPort.onMessage.addListener(handleAuditHostMessage);
      auditPort.onDisconnect.addListener(handleNativeDisconnect);
      
      // Probe status to verify connection
      sendSignedCommand({ command: 'status' });
      
      auditRuntime.state = 'running';
      auditRuntime.message = 'Reconnected successfully';
      pushAuditLog(auditRuntime.message);
      startHeartbeat();
      persistRuntime();
    } catch (err) {
      const errMsg = String(err?.message || err);
      console.warn(`[Worker] Reconnect attempt ${auditRuntime.reconnectAttempts} failed:`, errMsg);
      attemptReconnect();
    }
  }, delay);
}

function handleNativeDisconnect() {
  if (auditRuntime.running) {
    const runtimeErr = chrome.runtime.lastError?.message;
    auditRuntime.error = runtimeErr || auditRuntime.error || 'Native host disconnected unexpectedly';
    auditRuntime.message = auditRuntime.error;
    pushAuditLog(`WARNING: ${auditRuntime.error}`);
    stopHeartbeat();
    persistRuntime();
    
    // Attempt reconnect instead of failing immediately
    attemptReconnect();
  }
  auditPort = null;
}

function startAuditNativeRun(mode, stage) {
  if (auditRuntime.running) {
    return { ok: false, error: 'Audit already running' };
  }

  resetAuditRuntime();
  auditRuntime.running = true;
  auditRuntime.state = 'starting';
  auditRuntime.startedAt = new Date().toISOString();
  auditRuntime.reconnectAttempts = 0;

  try {
    auditPort = chrome.runtime.connectNative(AUDIT_NATIVE_HOST);
  } catch (err) {
    auditRuntime.running = false;
    auditRuntime.state = 'error';
    auditRuntime.error = String(err?.message || err);
    persistRuntime();
    return { ok: false, error: auditRuntime.error };
  }

  auditPort.onMessage.addListener(handleAuditHostMessage);
  auditPort.onDisconnect.addListener(handleNativeDisconnect);

  sendSignedCommand({ command: 'run', mode, stage });
  pushAuditLog(`Started audit run mode=${mode}${stage ? ` stage=${stage}` : ''}`);
  
  startHeartbeat();
  persistRuntime();

  return { ok: true, started: true };
}

function stopAuditNativeRun() {
  if (!auditPort || !auditRuntime.running) {
    return { ok: false, error: 'No running audit to stop' };
  }
  try {
    sendSignedCommand({ command: 'stop' });
    auditRuntime.state = 'stopping';
    auditRuntime.message = 'Stop requested';
    pushAuditLog('Stop requested');
    stopHeartbeat();
    persistRuntime();
    return { ok: true, stopping: true };
  } catch (err) {
    return { ok: false, error: String(err?.message || err) };
  }
}

// Restore runtime on worker startup
restoreRuntime();

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

      if (msg?.type === 'DAM_AUDIT_OPEN_OUTPUT') {
        // Note: Browser cannot open file:// URLs to arbitrary local paths for security
        // This will show the extension's bundled assets if they exist, or fail gracefully
        // For production, consider hosting a web-based file viewer or using chrome.downloads API
        try {
          // Try to open extension-relative path (safer than file://)
          const outputUrl = chrome.runtime.getURL('assets/audit/');
          chrome.tabs.create({ url: outputUrl });
          sendResponse({ ok: true });
        } catch (err) {
          // Fallback: show message that files must be accessed via File Explorer
          sendResponse({ 
            ok: false, 
            error: 'Cannot open local folder from extension. Please navigate to: C:\\Users\\colle\\Downloads\\aprimo_dam_crawler_extension\\assets\\audit\\' 
          });
        }
        return;
      }

      sendResponse({ ok: false, error: 'Unknown message type' });
    } catch (err) {
      sendResponse({ ok: false, error: String(err?.message || err) });
    }
  })();
  return true;
});
