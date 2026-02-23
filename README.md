# Aprimo DAM Collection Crawler (Chrome Extension, MV3)

Crawls Aprimo DAM collection pages with infinite/AJAX scrolling, collects image asset metadata, fetches detail pages, supports checkpoint/resume, and exports JSON/CSV.

## What it captures (v0.1)
- Asset item URL
- Item ID
- File name
- Preview URL (if visible)
- File type / content label
- Status (when available)
- Expiration date (when available)
- File size (from details page if available)
- Usage rights (label-based parser if present)
- Public URL (label-based parser if present)

## Resume / interruption support
Progress is checkpointed in `chrome.storage.local` every few seconds and during queue transitions.
If login/auth expires:
1. Log back into Aprimo
2. Return to the same collection page
3. Click **Start / Resume**

## Install (unpacked)
1. Open Chrome and visit `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select this folder (`aprimo_dam_crawler_extension`)

## Use
1. Open an Aprimo collection page (URL path like `/dam/collections/...`)
2. Click extension icon
3. Click **Start / Resume**
4. Optional: enable **Download preview images** if you want local images for later pHash indexing
5. Export JSON/CSV when done (or even mid-run for partial snapshots)

## Notes / caveats
- Uses resilient selectors (`a[href*="/items/"]`, `data-id="fields.ExpirationDate.value"`, etc.) to avoid brittle generated CSS classes.
- If Aprimo detail pages are SPA-only and `fetch(itemUrl)` returns a shell instead of data, the next upgrade is to intercept XHR/fetch payloads or scrape the side panel after clicking each item.
- Downloading preview images is optional and may require the preview CDN host to be covered by `host_permissions`.

## Next upgrades (suggested)
- Retry queue with exponential backoff and separate `retryable` vs `permanent` errors
- Background orchestration for large collections
- Side-panel scrape mode (click cards + parse visible panel)
- Export `page->image usage` and pHash pipeline companion scripts (Python)
