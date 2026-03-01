# Aprimo DAM Asset Crawler (Chrome Extension, MV3)

Crawls Aprimo DAM collection and space pages with infinite/AJAX scrolling, collects image asset metadata, fetches detail pages, supports checkpoint/resume, dedupes by Item ID, and exports JSON/CSV.

## What it captures (v0.2)
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
2. Return to the same collection or space page
3. Click **Start / Resume**

## Install (unpacked)
1. Open Chrome and visit `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select this folder (`aprimo_dam_crawler_extension`)

## Use
1. Open an Aprimo DAM page (URL path like `/dam/collections/...` or `/dam/spaces/...`)
2. Click extension icon
3. Click **Start / Resume**
4. Optional: enable **Download preview images** if you want local images for later pHash indexing
5. Export JSON/CSV when done (or even mid-run for partial snapshots)

## Single source + dedupe behavior
- Assets are stored in one master state keyed by `Item ID`.
- If the same asset appears in multiple collections/spaces, it is stored once and its `sourceKeys` membership list is expanded.
- Export includes dedupe/source fields: `seenInCount`, `sourceKeys`, `firstSeenAt`, `lastSeenAt`, `lastSeenSourceKey`.

## Recent updates (Feb 2026)
- Added support for Aprimo Space URLs (`/dam/spaces/...`) in addition to collection URLs.
- Added state migration so existing saved crawl progress continues to work without restarting.
- Added master-state dedupe by `Item ID` across collections and spaces.
- Added JSON import + merge support to restore/exported crawl state into local checkpoint storage.
- Added recheck flow for incomplete details (assets discovered where detail fetch was not completed).
- Replaced separate Start/Pause buttons with one toggle run button and visual icons.
- Moved extension assets into `images/` folder and updated icon paths.
- Added popup completion notifications for:
	- Successful completion (green)
	- Completed with errors (yellow)
- Added permanent storage architecture for scale: assets are persisted in IndexedDB (migrated from legacy checkpoint state), while `chrome.storage.local` now stores lightweight run/checkpoint metadata.

## Versioning note
- Current release: `0.2.0`
- Recommended convention for future changes:
	- Patch (`0.2.x`): bug fixes/UI tweaks
	- Minor (`0.x.0`): new crawler features, data fields, or workflow additions
	- Major (`x.0.0`): breaking export/schema or behavior changes

## Notes / caveats
- Uses resilient selectors (`a[href*="/items/"]`, `data-id="fields.ExpirationDate.value"`, etc.) to avoid brittle generated CSS classes.
- If Aprimo detail pages are SPA-only and `fetch(itemUrl)` returns a shell instead of data, the next upgrade is to intercept XHR/fetch payloads or scrape the side panel after clicking each item.
- Downloading preview images is optional and may require the preview CDN host to be covered by `host_permissions`.
- Citizensbank URLs compiled from Adobe Analytics and XML Sitemap (02/28/2026)

## Next upgrades (suggested)
- Retry queue with exponential backoff and separate `retryable` vs `permanent` errors
- Background orchestration for large collections
- Side-panel scrape mode (click cards + parse visible panel)
- Export `page->image usage` and pHash pipeline companion scripts (Python)

## Citizens vs DAM audit pipeline (Python)

This repo now includes a local Python audit pipeline to:
- Crawl `www.citizensbank.com` page URLs from `assets/citizensbank_urls.txt`
- Build fingerprints for Citizens images and DAM preview images
- Match Citizens images to DAM (exact hash first, then pHash)
- Produce filterable outputs in XLSX and HTML

### Run from extension via Native Messaging (Windows)

The extension can trigger the local Python pipeline through Chrome Native Messaging.

1. Get your extension ID from `chrome://extensions` (enable Developer mode).
2. Open PowerShell in the repo root and run the same sequence that was validated:
	- `cd C:\Users\colle\Downloads\aprimo_dam_crawler_extension`
	- `& .\.venv\Scripts\Activate.ps1`
	- `pip install -r .\scripts\requirements-audit.txt`
	- `$extId = "<YOUR_EXTENSION_ID>"`
	- `powershell -ExecutionPolicy Bypass -File .\scripts\register_native_host.ps1 -ExtensionId $extId -PythonExe "$PWD\.venv\Scripts\python.exe" -HostScript "$PWD\scripts\native_host.py"`
3. Verify registration:
	- `Get-ItemProperty "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.datastrux.dam_audit_host"`
	- `Get-Content "$env:LOCALAPPDATA\AprimoDamAuditNativeHost\com.datastrux.dam_audit_host.json"`
4. Reload the extension in Chrome.
5. In popup, use **Run Audit Pipeline** / **Stop Audit** and watch **Audit: ...** plus live progress during stage 01.

Notes:
- Native host name: `com.datastrux.dam_audit_host`
- Host script: `scripts/native_host.py`
- Host manifest template: `scripts/native_host_manifest.template.json`
- Registration script writes launcher: `%LOCALAPPDATA%\AprimoDamAuditNativeHost\run_dam_audit_host.cmd`

### Script order
- `scripts/01_crawl_citizens_images.py`
- `scripts/02_build_dam_fingerprints.py`
- `scripts/03_build_citizens_fingerprints.py`
- `scripts/04_match_assets.py`
- `scripts/05_build_reports.py`

Or run all stages:
- `scripts/run_audit_pipeline.py`

### Setup
1. Install Python dependencies:
	 - `pip install -r scripts/requirements-audit.txt`
2. Ensure inputs exist:
	 - `assets/citizensbank_urls.txt`
	 - `assets/aprimo_dam_assets_master_*.json`

### Run
- Full pipeline:
	- `python scripts/run_audit_pipeline.py`

### Outputs
- Intermediate data: `assets/audit/`
	- `citizens_pages.json`
	- `citizens_images.json`
	- `citizens_images_index.json`
	- `dam_fingerprints.json`
	- `citizens_fingerprints.json`
	- `match_results.json`
	- `unmatched_results.json`
	- `dam_internal_dupes.json`
	- `audit_master.csv`
	- `audit_master.json`
	- `audit_summary.json`
- Analyst-facing reports:
	- `reports/citizens_dam_audit.xlsx`
	- `reports/audit_report.html`

### Report flags
- `match_exact`: Citizens image has exact DAM hash match
- `match_phash`: Citizens image has pHash-based DAM match
- `unmatched` / `unmatched_error`: no DAM match or fingerprint error
- `needs_dam_upload = true`: Citizens-served image still needs DAM onboarding

### Redirect tracking (302/301 hop journey)

The crawler captures redirect journey per page in `assets/audit/citizens_pages.json`:
- `redirect_count`
- `redirect_hops[]` with `status_code`, `from_url`, `response_url`, `location`, `to_url`
- `final_url`

Crawler requests use a realistic Mozilla/Chrome desktop user agent string.

### Stage 01 progress + resume behavior

- Stage 01 (`scripts/01_crawl_citizens_images.py`) now emits structured progress (`current/total/percent`) consumed by the extension popup progress bar.
- Popup progress now shows both URL and image queue metrics during stage 01:
	- `URLs: <current>/<total> (<percent>%)`
	- `Images: <discovered> (<pending> pending)`
- If interrupted, stage 01 resumes automatically from `assets/audit/citizens_crawl_checkpoint.json` on next run.
- To force a fresh stage-01 crawl, run:
	- `python scripts/01_crawl_citizens_images.py --no-resume`