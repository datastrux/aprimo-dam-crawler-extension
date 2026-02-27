(() => {
  const STORAGE_KEY = 'damCrawlerState_v1';
  const CHECKPOINT_EVERY_MS = 5000;

  const runtime = {
    running: false,
    pausedByUser: false,
    checkpointTimer: null,
    options: { downloadPreviews: true }
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

  function uniqueStrings(values) {
    return Array.from(new Set((values || []).filter(v => typeof v === 'string' && v.trim())));
  }

  function normalizeImportedAsset(raw, fallbackSourceKey) {
    if (!raw || typeof raw !== 'object') return null;
    const itemUrl = raw.itemUrl || null;
    const itemId = raw.itemId || extractItemId(itemUrl);
    if (!itemId) return null;

    const sourceKeys = uniqueStrings([...(raw.sourceKeys || []), fallbackSourceKey]);
    return {
      itemId,
      fileName: raw.fileName || null,
      itemUrl,
      previewUrl: raw.previewUrl || null,
      contentTypeLabel: raw.contentTypeLabel || null,
      status: raw.status || null,
      expirationDate: normalizeDash(raw.expirationDate),
      usageRights: raw.usageRights || null,
      publicUrl: raw.publicUrl || null,
      fileSize: raw.fileSize || null,
      fileType: raw.fileType || inferFileType(raw.fileName, raw.contentTypeLabel),
      detailFetched: !!raw.detailFetched,
      detailFetchStatus: raw.detailFetchStatus ?? null,
      detailError: raw.detailError || null,
      downloadedPreview: !!raw.downloadedPreview,
      sourceKeys,
      seenInCount: sourceKeys.length,
      firstSeenAt: raw.firstSeenAt || nowIso(),
      lastSeenAt: raw.lastSeenAt || nowIso(),
      lastSeenSourceKey: raw.lastSeenSourceKey || sourceKeys[sourceKeys.length - 1] || null,
      raw: raw.raw && typeof raw.raw === 'object' ? raw.raw : {}
    };
  }

  function mergeAsset(existing, incoming) {
    existing.fileName ||= incoming.fileName;
    existing.itemUrl ||= incoming.itemUrl;
    existing.previewUrl ||= incoming.previewUrl;
    existing.contentTypeLabel ||= incoming.contentTypeLabel;
    existing.status ||= incoming.status;
    existing.expirationDate ??= incoming.expirationDate;
    existing.usageRights ||= incoming.usageRights;
    existing.publicUrl ||= incoming.publicUrl;
    existing.fileSize ||= incoming.fileSize;
    existing.fileType ||= incoming.fileType;
    existing.downloadedPreview = !!(existing.downloadedPreview || incoming.downloadedPreview);

    existing.sourceKeys = uniqueStrings([...(existing.sourceKeys || []), ...(incoming.sourceKeys || [])]);
    existing.seenInCount = existing.sourceKeys.length;
    existing.firstSeenAt ||= incoming.firstSeenAt || nowIso();
    existing.lastSeenAt = nowIso();
    existing.lastSeenSourceKey = incoming.lastSeenSourceKey || existing.lastSeenSourceKey || existing.sourceKeys[existing.sourceKeys.length - 1] || null;

    if (incoming.detailFetched) {
      existing.detailFetched = true;
      existing.detailError = null;
      existing.detailFetchStatus = incoming.detailFetchStatus ?? existing.detailFetchStatus ?? null;
      existing.status ||= incoming.status;
      existing.expirationDate ??= incoming.expirationDate;
      existing.fileSize ||= incoming.fileSize;
      existing.usageRights ||= incoming.usageRights;
      existing.publicUrl ||= incoming.publicUrl;
    } else if (!existing.detailFetched) {
      existing.detailError ||= incoming.detailError;
      existing.detailFetchStatus ??= incoming.detailFetchStatus;
    }
  }

  function rebuildQueues(options = {}) {
    const { requeueIncomplete = false, clearErrors = false } = options;
    const itemIds = Object.keys(state.assets || {});
    const pending = new Set((state.queue.detailPending || []).filter(id => !!state.assets[id]));
    const inProgress = new Set((state.queue.detailInProgress || []).filter(id => !!state.assets[id]));
    const done = new Set((state.queue.detailDone || []).filter(id => !!state.assets[id]));
    const errors = new Set((state.queue.detailErrors || []).filter(id => !!state.assets[id]));

    let requeuedCount = 0;

    for (const itemId of itemIds) {
      const asset = state.assets[itemId];
      if (!asset) continue;

      if (asset.detailFetched) {
        done.add(itemId);
        pending.delete(itemId);
        inProgress.delete(itemId);
        errors.delete(itemId);
        continue;
      }

      done.delete(itemId);

      if (clearErrors) {
        errors.delete(itemId);
        asset.detailError = null;
        asset.detailFetchStatus = null;
      }

      const shouldQueue = requeueIncomplete && !!asset.itemUrl;
      if (shouldQueue && !pending.has(itemId) && !inProgress.has(itemId)) {
        pending.add(itemId);
        requeuedCount++;
      }
    }

    state.queue.detailPending = Array.from(pending);
    state.queue.detailInProgress = Array.from(inProgress);
    state.queue.detailDone = Array.from(done);
    state.queue.detailErrors = Array.from(errors);
    state.stats.detailErrors = state.queue.detailErrors.length;

    return { requeuedCount };
  }

  async function importStatePayload(payload) {
    if (!payload || typeof payload !== 'object') throw new Error('Invalid import payload');
    if (!Array.isArray(payload.assets)) throw new Error('Import JSON must contain an assets array');

    const importedSource = payload.source?.sourceKey || null;
    const importedKnownSources = payload.knownSources && typeof payload.knownSources === 'object' ? payload.knownSources : {};

    state.knownSources ||= {};
    for (const [key, value] of Object.entries(importedKnownSources)) {
      if (!key || !value || typeof value !== 'object') continue;
      state.knownSources[key] ||= {
        sourceType: value.sourceType || null,
        sourceId: value.sourceId || null,
        url: value.url || location.href,
        firstSeenAt: value.firstSeenAt || nowIso(),
        lastSeenAt: value.lastSeenAt || nowIso()
      };
      state.knownSources[key].lastSeenAt = nowIso();
    }
    ensureKnownSource(currentSource());

    let added = 0;
    let updated = 0;
    let skipped = 0;

    for (const rawAsset of payload.assets) {
      const incoming = normalizeImportedAsset(rawAsset, importedSource);
      if (!incoming) {
        skipped++;
        continue;
      }

      const existing = state.assets[incoming.itemId];
      if (!existing) {
        state.assets[incoming.itemId] = incoming;
        if (!incoming.detailFetched && incoming.itemUrl) queueIfMissing(incoming.itemId);
        if (incoming.detailFetched && !state.queue.detailDone.includes(incoming.itemId)) {
          state.queue.detailDone.push(incoming.itemId);
        }
        added++;
      } else {
        mergeAsset(existing, incoming);
        updated++;
      }
    }

    rebuildQueues({ requeueIncomplete: false, clearErrors: false });
    await saveCheckpoint();
    return { added, updated, skipped };
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

  function getScrollContext() {
    const root = document.scrollingElement || document.documentElement;
    const candidates = Array.from(document.querySelectorAll('main, [role="main"], [role="grid"], [role="list"], [aria-label*="Assets" i], [class*="scroll" i], [class*="virtual" i]'));

    let best = null;
    let bestScore = 0;
    for (const el of candidates) {
      if (!(el instanceof HTMLElement)) continue;
      const overflowY = getComputedStyle(el).overflowY;
      if (!/(auto|scroll|overlay)/i.test(overflowY)) continue;
      const scrollable = el.scrollHeight - el.clientHeight;
      if (scrollable < 200) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 200 || rect.height < 200) continue;
      const score = scrollable + rect.height;
      if (score > bestScore) {
        best = el;
        bestScore = score;
      }
    }

    if (best) {
      return {
        type: 'element',
        viewportHeight: best.clientHeight,
        currentY: best.scrollTop,
        maxY: Math.max(best.scrollHeight - best.clientHeight, 0),
        scrollTo(y) { best.scrollTop = y; }
      };
    }

    return {
      type: 'window',
      viewportHeight: Math.max(window.innerHeight || 0, 400),
      currentY: window.scrollY,
      maxY: Math.max(root.scrollHeight - Math.max(window.innerHeight || 0, 400), 0),
      scrollTo(y) { window.scrollTo({ top: y, behavior: 'auto' }); }
    };
  }

  async function scrollDiscoverLoop() {
    let idleRounds = 0;
    let lastCount = Object.keys(state.assets).length;
    let lastExtent = Math.max((document.scrollingElement || document.documentElement).scrollHeight, 0);

    while (runtime.running && !runtime.pausedByUser && !state.authExpired) {
      state.stats.scrollRounds++;
      const beforeAdded = collectVisibleCards();

      const ctx = getScrollContext();
      const scrollStep = Math.max(Math.floor(ctx.viewportHeight * 0.9), 300);
      const targetY = Math.min(ctx.currentY + scrollStep, ctx.maxY);
      ctx.scrollTo(targetY);

      await sleep(900);
      const afterAdded = collectVisibleCards();

      const currentCount = Object.keys(state.assets).length;
      const nextCtx = getScrollContext();
      const currentExtent = Math.max((document.scrollingElement || document.documentElement).scrollHeight, nextCtx.maxY + nextCtx.viewportHeight);
      const nearBottom = (nextCtx.currentY + nextCtx.viewportHeight) >= (nextCtx.maxY - 8);
      const noGrowth = currentCount === lastCount && currentExtent === lastExtent && beforeAdded === 0 && afterAdded === 0;

      if (nearBottom && noGrowth) {
        nextCtx.scrollTo(nextCtx.maxY);
        await sleep(700);
        const afterPokeAdded = collectVisibleCards();
        const pokeCount = Object.keys(state.assets).length;
        const pokeCtx = getScrollContext();
        const pokeExtent = Math.max((document.scrollingElement || document.documentElement).scrollHeight, pokeCtx.maxY + pokeCtx.viewportHeight);
        const stillNoGrowth = pokeCount === currentCount && pokeExtent === currentExtent && afterPokeAdded === 0;
        idleRounds = stillNoGrowth ? idleRounds + 1 : 0;
        lastCount = pokeCount;
        lastExtent = pokeExtent;
      } else {
        idleRounds = noGrowth ? idleRounds + 1 : 0;
        lastCount = currentCount;
        lastExtent = currentExtent;
      }

      if (idleRounds >= 12) {
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

  async function recheckIncomplete(options = {}) {
    if (runtime.running) throw new Error('Crawler is already running');

    runtime.running = true;
    runtime.pausedByUser = false;
    state.authExpired = false;
    runtime.options = { ...runtime.options, ...options };
    startCheckpointLoop();

    try {
      const { requeuedCount } = rebuildQueues({ requeueIncomplete: true, clearErrors: true });
      state.discoveredComplete = true;
      await saveCheckpoint();
      await detailWorkerLoop();
      await saveCheckpoint();
      return { processed: requeuedCount };
    } finally {
      runtime.running = false;
      stopCheckpointLoop();
      await saveCheckpoint().catch(() => {});
    }
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
          case 'DAM_CRAWLER_IMPORT_STATE': {
            const result = await importStatePayload(msg.payload);
            sendResponse({ ok: true, ...result, stats: getStats() });
            return;
          }
          case 'DAM_CRAWLER_RECHECK_INCOMPLETE': {
            const result = await recheckIncomplete(msg.options || {});
            sendResponse({ ok: true, ...result, stats: getStats() });
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
