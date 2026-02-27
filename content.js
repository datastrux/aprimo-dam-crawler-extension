(() => {
  const STORAGE_KEY = 'damCrawlerState_v1';
  const CHECKPOINT_EVERY_MS = 5000;

  const runtime = {
    running: false,
    pausedByUser: false,
    checkpointTimer: null,
    options: { downloadPreviews: false }
  };

  let state = {
    version: 1,
    pageUrl: location.href,
    pageOrigin: location.origin,
    source: extractSourceContext(location.href),
    knownSources: {},
    discoveredComplete: false,
    lastScrollY: 0,
    authExpired: false,
    assets: {}, // itemId -> asset
    queue: {
      detailPending: [],
      detailInProgress: [],
      detailDone: [],
      detailErrors: []
    },
    stats: {
      startedAt: null,
      updatedAt: null,
      scrollRounds: 0,
      visibleScans: 0,
      detailFetched: 0,
      detailErrors: 0
    }
  };

  function nowIso() { return new Date().toISOString(); }
  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function absUrl(href) { try { return new URL(href, location.origin).href; } catch { return null; } }
  function extractSourceContext(url) {
    const m = String(url).match(/\/dam\/(collections|spaces)\/([a-f0-9]+)/i);
    if (!m) return { sourceType: null, sourceId: null, sourceKey: null };
    const sourceType = m[1].toLowerCase();
    const sourceId = m[2].toLowerCase();
    return { sourceType, sourceId, sourceKey: `${sourceType}:${sourceId}` };
  }
  function extractItemId(url) { const m = String(url).match(/\/items\/([a-f0-9]+)/i); return m ? m[1] : null; }

  function currentSource() {
    return extractSourceContext(location.href);
  }

  function ensureKnownSource(source = currentSource()) {
    if (!source?.sourceKey) return;
    state.knownSources[source.sourceKey] ||= {
      sourceType: source.sourceType,
      sourceId: source.sourceId,
      url: location.href,
      firstSeenAt: nowIso(),
      lastSeenAt: nowIso()
    };
    state.knownSources[source.sourceKey].lastSeenAt = nowIso();
    state.knownSources[source.sourceKey].url = location.href;
  }

  function migrateState(saved) {
    if (!saved || typeof saved !== 'object') return null;
    const migrated = { ...saved };

    if (!migrated.source) {
      const legacyCollectionId = migrated.collectionId || extractSourceContext(migrated.pageUrl || location.href).sourceId;
      if (legacyCollectionId) {
        migrated.source = {
          sourceType: 'collections',
          sourceId: legacyCollectionId,
          sourceKey: `collections:${legacyCollectionId}`
        };
      } else {
        migrated.source = currentSource();
      }
    }

    migrated.knownSources ||= {};
    if (migrated.source?.sourceKey && !migrated.knownSources[migrated.source.sourceKey]) {
      migrated.knownSources[migrated.source.sourceKey] = {
        sourceType: migrated.source.sourceType,
        sourceId: migrated.source.sourceId,
        url: migrated.pageUrl || location.href,
        firstSeenAt: nowIso(),
        lastSeenAt: nowIso()
      };
    }

    migrated.assets ||= {};
    for (const asset of Object.values(migrated.assets)) {
      if (!asset || typeof asset !== 'object') continue;
      const sourceSet = new Set(Array.isArray(asset.sourceKeys) ? asset.sourceKeys : []);
      if (!sourceSet.size && migrated.source?.sourceKey) sourceSet.add(migrated.source.sourceKey);
      asset.sourceKeys = Array.from(sourceSet);
      asset.seenInCount = asset.sourceKeys.length;
      asset.firstSeenAt ||= nowIso();
      asset.lastSeenAt ||= nowIso();
      asset.lastSeenSourceKey ||= asset.sourceKeys[asset.sourceKeys.length - 1] || null;
    }

    return migrated;
  }

  async function loadCheckpoint() {
    const obj = await chrome.storage.local.get(STORAGE_KEY);
    const saved = obj?.[STORAGE_KEY];
    if (!saved) return false;
    const migrated = migrateState(saved);
    if (!migrated) return false;
    state = {
      ...state,
      ...migrated,
      pageUrl: location.href,
      pageOrigin: location.origin,
      source: currentSource()
    };
    ensureKnownSource(state.source);
    return true;
  }

  async function saveCheckpoint() {
    state.pageUrl = location.href;
    state.source = currentSource();
    ensureKnownSource(state.source);
    state.lastScrollY = window.scrollY;
    state.stats.updatedAt = nowIso();
    await chrome.storage.local.set({ [STORAGE_KEY]: state });
  }

  async function clearCheckpoint() {
    await chrome.storage.local.remove(STORAGE_KEY);
  }

  function startCheckpointLoop() {
    stopCheckpointLoop();
    runtime.checkpointTimer = setInterval(() => saveCheckpoint().catch(console.warn), CHECKPOINT_EVERY_MS);
  }
  function stopCheckpointLoop() {
    if (runtime.checkpointTimer) clearInterval(runtime.checkpointTimer);
    runtime.checkpointTimer = null;
  }

  function getStats() {
    const pending = state.queue.detailPending.length;
    const inProgress = state.queue.detailInProgress.length;
    const errors = state.queue.detailErrors.length;
    const completedBase = !!state.discoveredComplete && !runtime.running && !state.authExpired && pending === 0 && inProgress === 0;
    const completedSuccessfully = completedBase && errors === 0;
    const completedWithErrors = completedBase && errors > 0;
    return {
      running: runtime.running,
      assetCount: Object.keys(state.assets).length,
      detailDone: state.queue.detailDone.length,
      detailErrors: errors,
      detailPending: pending,
      detailInProgress: inProgress,
      authExpired: !!state.authExpired,
      discoveredComplete: !!state.discoveredComplete,
      completedSuccessfully,
      completedWithErrors
    };
  }

  function queueIfMissing(itemId) {
    if (!itemId) return;
    const q = state.queue;
    if (q.detailDone.includes(itemId) || q.detailPending.includes(itemId) || q.detailInProgress.includes(itemId)) return;
    q.detailPending.push(itemId);
  }

  function removeFrom(arr, value) {
    const idx = arr.indexOf(value);
    if (idx >= 0) arr.splice(idx, 1);
  }

  function collectVisibleCards() {
    state.stats.visibleScans++;
    let added = 0;
    const source = currentSource();
    ensureKnownSource(source);

    const anchors = Array.from(document.querySelectorAll('a[href*="/items/"]'));
    for (const a of anchors) {
      const itemUrl = absUrl(a.getAttribute('href'));
      const itemId = extractItemId(itemUrl);
      if (!itemId) continue;

      const card = a.closest('[role="listitem"]') || a.closest('article') || a.parentElement;
      const fileName = (a.getAttribute('title') || a.textContent || '').trim() || null;

      const typeEl = card?.querySelector('p[title]');
      const contentTypeLabel = typeEl?.getAttribute('title') || typeEl?.textContent?.trim() || null;

      const statusField = card?.querySelector('[data-id="fields.Status"] p, [data-id="fields.Status"] .MuiTypography-root p');
      const status = statusField?.textContent?.trim() || null;

      const expField = card?.querySelector('[data-id="fields.ExpirationDate.value"] p, [data-id="fields.ExpirationDate.value"] .MuiTypography-root');
      const expirationDate = normalizeDash(expField?.textContent?.trim());

      const previewImg = card?.querySelector('img[src]');
      const previewUrl = previewImg?.src ? absUrl(previewImg.src) : null;

      if (!state.assets[itemId]) {
        state.assets[itemId] = {
          itemId,
          fileName,
          itemUrl,
          previewUrl,
          contentTypeLabel,
          status,
          expirationDate,
          usageRights: null,
          publicUrl: null,
          fileSize: null,
          fileType: inferFileType(fileName, contentTypeLabel),
          detailFetched: false,
          detailFetchStatus: null,
          detailError: null,
          downloadedPreview: false,
          sourceKeys: source?.sourceKey ? [source.sourceKey] : [],
          seenInCount: source?.sourceKey ? 1 : 0,
          firstSeenAt: nowIso(),
          lastSeenAt: nowIso(),
          lastSeenSourceKey: source?.sourceKey || null,
          raw: {}
        };
        added++;
        queueIfMissing(itemId);
      } else {
        const x = state.assets[itemId];
        x.fileName ||= fileName;
        x.itemUrl ||= itemUrl;
        x.previewUrl ||= previewUrl;
        x.contentTypeLabel ||= contentTypeLabel;
        x.status ||= status;
        x.expirationDate ??= expirationDate;
        x.fileType ||= inferFileType(fileName, contentTypeLabel);
        x.sourceKeys ||= [];
        if (source?.sourceKey && !x.sourceKeys.includes(source.sourceKey)) x.sourceKeys.push(source.sourceKey);
        x.seenInCount = x.sourceKeys.length;
        x.lastSeenAt = nowIso();
        x.lastSeenSourceKey = source?.sourceKey || x.lastSeenSourceKey || null;
      }
    }

    return added;
  }

  function normalizeDash(v) {
    if (v == null) return null;
    const t = String(v).trim();
    if (!t || t === '—' || t === '-') return null;
    return t;
  }

  function inferFileType(fileName, contentTypeLabel) {
    if (fileName && fileName.includes('.')) return fileName.split('.').pop().toLowerCase();
    const m = String(contentTypeLabel || '').match(/\(([^)]+)\)/);
    return m ? m[1].toLowerCase() : null;
  }

  function textNearLabel(root, labelText) {
    const labelEls = Array.from(root.querySelectorAll('label, span, p, div'));
    const target = labelText.toLowerCase();
    for (const el of labelEls) {
      const txt = (el.textContent || '').trim().replace(/\s+/g, ' ');
      if (txt.toLowerCase() !== target) continue;
      const box = el.closest('div') || el.parentElement;
      if (!box) continue;
      const candidates = Array.from(box.querySelectorAll('p, div, span'))
        .map(n => (n.textContent || '').trim().replace(/\s+/g, ' '))
        .filter(Boolean)
        .filter(v => v.toLowerCase() !== target);
      if (candidates.length) return normalizeDash(candidates[candidates.length - 1]);
    }
    return null;
  }

  function parseDetailHtml(html, asset) {
    const doc = new DOMParser().parseFromString(html, 'text/html');

    const titleText = (doc.querySelector('title')?.textContent || '').toLowerCase();
    const bodyText = (doc.body?.textContent || '').toLowerCase();
    if (titleText.includes('sign in') || bodyText.includes('sign in') || bodyText.includes('login')) {
      throw new Error('AUTH_EXPIRED_OR_LOGIN_PAGE');
    }

    const status = normalizeDash(doc.querySelector('[data-id="fields.Status"] p')?.textContent) || textNearLabel(doc, 'Status');
    const expirationDate = normalizeDash(doc.querySelector('[data-id="fields.ExpirationDate.value"] p')?.textContent) || textNearLabel(doc, 'Expiration Date');
    const fileSize = textNearLabel(doc, 'File size');
    const usageRights = textNearLabel(doc, 'Usage Rights') || textNearLabel(doc, 'Usage rights');
    const publicUrl = textNearLabel(doc, 'Public URL') || textNearLabel(doc, 'Public Url');

    return { status, expirationDate, fileSize, usageRights, publicUrl };
  }

  async function fetchDetailForItem(itemId) {
    const asset = state.assets[itemId];
    if (!asset?.itemUrl) return;

    removeFrom(state.queue.detailPending, itemId);
    if (!state.queue.detailInProgress.includes(itemId)) state.queue.detailInProgress.push(itemId);
    await saveCheckpoint();

    try {
      const resp = await fetch(asset.itemUrl, { credentials: 'include' });
      asset.detailFetchStatus = resp.status;
      if (resp.status === 401 || resp.status === 403) throw new Error('AUTH_EXPIRED');
      if (!resp.ok) throw new Error(`HTTP_${resp.status}`);
      const html = await resp.text();
      const parsed = parseDetailHtml(html, asset);
      Object.assign(asset, parsed, {
        detailFetched: true,
        detailError: null
      });
      removeFrom(state.queue.detailInProgress, itemId);
      if (!state.queue.detailDone.includes(itemId)) state.queue.detailDone.push(itemId);
      state.stats.detailFetched++;

      if (runtime.options.downloadPreviews && asset.previewUrl && !asset.downloadedPreview) {
        await requestPreviewDownload(asset).catch(err => {
          console.warn('Preview download failed', itemId, err);
        });
      }
    } catch (err) {
      const msg = String(err?.message || err);
      asset.detailFetched = false;
      asset.detailError = msg;
      removeFrom(state.queue.detailInProgress, itemId);
      if (msg.includes('AUTH_EXPIRED') || msg.includes('LOGIN_PAGE')) {
        state.authExpired = true;
        if (!state.queue.detailPending.includes(itemId)) state.queue.detailPending.unshift(itemId);
      } else {
        if (!state.queue.detailErrors.includes(itemId)) state.queue.detailErrors.push(itemId);
      }
      state.stats.detailErrors = state.queue.detailErrors.length;
      throw err;
    }
  }

  async function requestPreviewDownload(asset) {
    const current = currentSource();
    const sourceSegment = current?.sourceId || 'source';
    const filename = sanitizePath(`aprimo_dam_previews/${sourceSegment}/${asset.itemId}__${asset.fileName || 'asset'}.${asset.fileType || 'bin'}`)
      .replace(/\.(jpg|jpeg|png|gif|webp)\.(jpg|jpeg|png|gif|webp)$/i, '.$1');
    const res = await chrome.runtime.sendMessage({ type: 'DAM_CRAWLER_DOWNLOAD_URL', url: asset.previewUrl, filename });
    if (res?.ok) asset.downloadedPreview = true;
    return res;
  }

  function sanitizePath(s) {
    return String(s).replace(/[<>:"|?*]/g, '_').replace(/\\/g, '/');
  }

  async function detailWorkerLoop() {
    const concurrency = 3;
    const workers = Array.from({ length: concurrency }, (_, idx) => worker(idx + 1));
    await Promise.all(workers);

    async function worker() {
      while (runtime.running && !runtime.pausedByUser) {
        if (state.authExpired) break;
        const nextId = state.queue.detailPending[0];
        if (!nextId) {
          await sleep(250);
          if (state.discoveredComplete && !state.queue.detailPending.length && !state.queue.detailInProgress.length) break;
          continue;
        }
        try {
          await fetchDetailForItem(nextId);
          await sleep(150);
        } catch (e) {
          if (String(e?.message || e).includes('AUTH_EXPIRED')) break;
          await sleep(300);
        }
      }
    }
  }

  async function scrollDiscoverLoop() {
    let idleRounds = 0;
    let lastCount = Object.keys(state.assets).length;
    let lastHeight = document.documentElement.scrollHeight;

    while (runtime.running && !runtime.pausedByUser && !state.authExpired) {
      state.stats.scrollRounds++;
      const beforeAdded = collectVisibleCards();
      const h = document.documentElement.scrollHeight;
      window.scrollTo({ top: h, behavior: 'smooth' });
      await sleep(1200);
      const afterAdded = collectVisibleCards();

      const currentCount = Object.keys(state.assets).length;
      const currentHeight = document.documentElement.scrollHeight;
      const noGrowth = currentCount === lastCount && currentHeight === lastHeight && beforeAdded === 0 && afterAdded === 0;
      idleRounds = noGrowth ? idleRounds + 1 : 0;
      lastCount = currentCount;
      lastHeight = currentHeight;

      if (idleRounds >= 8) {
        state.discoveredComplete = true;
        break;
      }
      await saveCheckpoint();
    }
  }

  async function runMain(options = {}) {
    if (runtime.running) return;
    runtime.running = true;
    runtime.pausedByUser = false;
    state.authExpired = false;
    runtime.options = { ...runtime.options, ...options };
    state.stats.startedAt ||= nowIso();
    await loadCheckpoint();
    state.source = currentSource();
    ensureKnownSource(state.source);
    state.discoveredComplete = false;
    startCheckpointLoop();

    try {
      collectVisibleCards();
      await Promise.all([scrollDiscoverLoop(), detailWorkerLoop()]);
      await saveCheckpoint();
    } finally {
      runtime.running = false;
      stopCheckpointLoop();
      await saveCheckpoint().catch(() => {});
    }
  }

  function pauseMain() {
    runtime.pausedByUser = true;
    runtime.running = false;
    stopCheckpointLoop();
    saveCheckpoint().catch(console.warn);
  }

  async function exportJson() {
    const payload = {
      source: state.source,
      knownSources: state.knownSources,
      sourceCount: Object.keys(state.knownSources || {}).length,
      sourceUrl: location.href,
      exportedAt: nowIso(),
      stats: state.stats,
      discoveredComplete: state.discoveredComplete,
      authExpired: state.authExpired,
      assetCount: Object.keys(state.assets).length,
      assets: Object.values(state.assets)
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const blobUrl = URL.createObjectURL(blob);
    const filename = `aprimo_dam_assets_master_${Date.now()}.json`;
    const res = await chrome.runtime.sendMessage({ type: 'DAM_CRAWLER_DOWNLOAD_BLOB', blobUrl, filename });
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1500);
    return res;
  }

  async function exportCsv() {
    const rows = Object.values(state.assets);
    const headers = [
      'itemId','fileName','itemUrl','previewUrl','contentTypeLabel','fileType','status','expirationDate','usageRights','publicUrl','fileSize','detailFetched','detailFetchStatus','detailError','downloadedPreview','seenInCount','sourceKeys','firstSeenAt','lastSeenAt','lastSeenSourceKey'
    ];
    const csv = [headers.join(',')].concat(rows.map(r => headers.map(h => {
      if (h === 'sourceKeys') return csvEscape((r.sourceKeys || []).join('|'));
      return csvEscape(r[h]);
    }).join(','))).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const blobUrl = URL.createObjectURL(blob);
    const filename = `aprimo_dam_assets_master_${Date.now()}.csv`;
    const res = await chrome.runtime.sendMessage({ type: 'DAM_CRAWLER_DOWNLOAD_BLOB', blobUrl, filename });
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1500);
    return res;
  }

  function csvEscape(v) {
    if (v == null) return '';
    const s = String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  async function resetState() {
    pauseMain();
    state = {
      version: 1,
      pageUrl: location.href,
      pageOrigin: location.origin,
      source: currentSource(),
      knownSources: {},
      discoveredComplete: false,
      lastScrollY: 0,
      authExpired: false,
      assets: {},
      queue: { detailPending: [], detailInProgress: [], detailDone: [], detailErrors: [] },
      stats: { startedAt: null, updatedAt: null, scrollRounds: 0, visibleScans: 0, detailFetched: 0, detailErrors: 0 }
    };
    ensureKnownSource(state.source);
    await clearCheckpoint();
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    (async () => {
      try {
        switch (msg?.type) {
          case 'DAM_CRAWLER_STATUS':
            {
              const stats = getStats();
              const message = state.authExpired
                ? 'Auth expired. Re-login and click Start / Resume.'
                : (stats.completedSuccessfully
                  ? 'Crawl completed successfully.'
                  : (stats.completedWithErrors ? 'Crawl completed with errors.' : 'Ready'));
              sendResponse({ ok: true, message, stats });
            }
            return;
          case 'DAM_CRAWLER_START':
            runMain(msg.options || {}).catch(console.warn);
            sendResponse({ ok: true, started: true });
            return;
          case 'DAM_CRAWLER_PAUSE':
            pauseMain();
            sendResponse({ ok: true });
            return;
          case 'DAM_CRAWLER_SCAN_VISIBLE': {
            const added = collectVisibleCards();
            await saveCheckpoint();
            sendResponse({ ok: true, added, stats: getStats() });
            return;
          }
          case 'DAM_CRAWLER_EXPORT_JSON':
            sendResponse(await exportJson());
            return;
          case 'DAM_CRAWLER_EXPORT_CSV':
            sendResponse(await exportCsv());
            return;
          case 'DAM_CRAWLER_RESET':
            await resetState();
            sendResponse({ ok: true });
            return;
          default:
            sendResponse({ ok: false, error: 'Unknown command' });
            return;
        }
      } catch (err) {
        sendResponse({ ok: false, error: String(err?.message || err) });
      }
    })();
    return true;
  });

  loadCheckpoint().then(found => {
    if (found) {
      // restore scroll position for convenience, not required
      if (typeof state.lastScrollY === 'number' && state.lastScrollY > 0) {
        setTimeout(() => window.scrollTo(0, state.lastScrollY), 500);
      }
    }
  }).catch(console.warn);

  console.log('[Aprimo DAM Crawler] content script loaded');
})();
