// Minimal background worker for downloads and future queue orchestration.

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
        const { url, filename } = msg;
        const downloadId = await chrome.downloads.download({ url, filename, saveAs: false, conflictAction: 'uniquify' });
        sendResponse({ ok: true, downloadId });
        return;
      }

      sendResponse({ ok: false, error: 'Unknown message type' });
    } catch (err) {
      sendResponse({ ok: false, error: String(err?.message || err) });
    }
  })();
  return true;
});
