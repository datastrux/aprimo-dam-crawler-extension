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

### Audit pipeline reliability & reconnect (March 2026)

The extension service worker now includes production-ready reconnect and persistence:

**Automatic reconnect**
- If native host disconnects during a run (process crash, timeout, etc.), the worker automatically attempts to reconnect.
- Uses exponential backoff: 1s → 2s → 4s → 8s → ... up to 30s max delay.
- Max 10 reconnect attempts before marking audit as failed.
- Popup shows `Audit: reconnecting (attempt X/10)` status during recovery.

**Persistent state across worker restarts**
- Extension service worker (MV3) may suspend/restart at any time.
- Audit runtime state is persisted to `chrome.storage.local` on every update.
- On worker restart, state is restored and reconnect attempted if audit was running.
- Audit progress survives popup close/reopen and worker lifecycle events.

**Heartbeat & stale detection**
- Worker sends `status` command to native host every 2 seconds while audit is running.
- If no response for 10 seconds (5 missed heartbeats), popup shows `⚠ No response (may be hung)` warning.
- Helps detect hung Python processes vs. active crawl work.

**Audit states**
- `idle` — No audit running
- `starting` — Launching native host and pipeline
- `running` — Active stage execution, progress updates flowing
- `reconnecting` — Native host disconnected, attempting recovery
- `stopping` — Stop requested, waiting for graceful shutdown
- `completed` — All stages finished successfully
- `error` — Pipeline failed or max reconnect attempts exhausted

**Verifying native connectivity**
1. Check extension service worker console (`chrome://extensions` → Inspect views → Service Worker):
	 - Look for `[Worker DEBUG]` heartbeat logs every ~2s
	 - Verify `auditRuntime.lastHeartbeatAt` timestamp updates
2. Confirm native host is running:
	 - PowerShell: `Get-Process python | Where-Object { $_.CommandLine -match 'native_host.py' }`
3. Check native host stderr:
	 - Look for `[NativeHost DEBUG]` progress parse logs
	 - Verify `runId` and timestamps in emitted events

### Standalone audit pipeline (no extension)

For command-line or CI/CD workflows, the audit pipeline can run independently with **live progress monitoring** and **persistent status tracking**.

**Run standalone orchestrator**
```powershell
# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Run all stages with live progress
python scripts/run_audit_standalone.py

# With log file
python scripts/run_audit_standalone.py --log-file audit.log

# Custom status file path
python scripts/run_audit_standalone.py --status-file custom_status.json
```

**Live progress features**
- ✅ **Inline progress bars** — Visual progress during stage-01 crawl with URL/image counters
- ✅ **Pipeline percentage** — Overall completion shown as `[2/5] Stage | Pipeline: 40%`
- ✅ **Per-stage duration** — Timing for each completed stage
- ✅ **Summary table** — Final report with all stages, status, and durations
- ✅ **Persistent status file** — JSON file at `assets/audit/pipeline_status.json` for external monitoring

**Example output**
```
🚀 Starting Aprimo DAM Audit Pipeline (Standalone Mode)
Status file: C:\...\assets\audit\pipeline_status.json

================================================================================
[1/5] 01_crawl_citizens_images.py | Pipeline: 0%
================================================================================
AUDIT_PROGRESS ...
  └─ [████████████████████░░░░░░░░░░░░░░░░░░░░░] 52.0% | 52/100 | 350 images | 298 pending
✅ 01_crawl_citizens_images.py completed successfully (duration: 45.2s)
   Final: 100/100 items processed

[2/5] 02_build_dam_fingerprints.py | Pipeline: 20%
================================================================================
...
```

**External monitoring with PowerShell**

Open a separate terminal to watch live progress:
```powershell
.\scripts\watch_audit.ps1
```

This displays a live dashboard:
```
═══════════════════════════════════════════════════════════
 🔍 AUDIT PIPELINE MONITOR
═══════════════════════════════════════════════════════════

Status:   RUNNING
Stage:    01_crawl_citizens_images.py
Progress: 52.0% (2/5 stages)
          [█████████████████████████░░░░░░░░░░░░░░░░░░░░░]

───────────────────────────────────────────────────────────
 STAGES
───────────────────────────────────────────────────────────
 ✅ 01_crawl_citizens_images.py       COMPLETED    45.2s
 ⏳ 02_build_dam_fingerprints.py      RUNNING
    └─ URLs: 52/100 (52.0%)
    └─ Images: 350 detected (298 pending)
 ○  03_build_citizens_fingerprints.py PENDING
 ○  04_match_assets.py                PENDING
 ○  05_build_reports.py               PENDING

───────────────────────────────────────────────────────────
Started:  2026-03-02 14:30:15
Elapsed:  67.3s
Updated:  2026-03-02 14:31:22
```

**Persistent status file format**

The `assets/audit/pipeline_status.json` file contains:
```json
{
  "status": "running",
  "current_stage": "01_crawl_citizens_images.py",
  "current_stage_num": 1,
  "total_stages": 5,
  "pipeline_percent": 20.0,
  "started_at": 1709391015.234,
  "updated_at": 1709391082.567,
  "stages": {
    "01_crawl_citizens_images.py": {
      "status": "completed",
      "started_at": 1709391015.234,
      "completed_at": 1709391060.456,
      "duration_seconds": 45.222,
      "exit_code": 0,
      "last_progress": {
        "urls_completed": 100,
        "urls_total": 100,
        "images_detected": 850,
        "images_remaining": 0
      }
    },
    "02_build_dam_fingerprints.py": { "status": "running", ... }
  }
}
```

**Use cases for status file**
- **CI/CD integration** — GitHub Actions / Jenkins can poll status and react to stage changes
- **Team dashboards** — Web UI can display progress to multiple viewers
- **Slack/email alerts** — External scripts send notifications on stage completion
- **Resume logic** — Crash recovery can skip completed stages
- **Performance tracking** — Archive snapshots to analyze stage duration trends over time

**Run individual stages**
```powershell
python scripts/01_crawl_citizens_images.py
python scripts/02_build_dam_fingerprints.py
# etc.
```

**When to use standalone vs extension**
- **Extension**: interactive monitoring, popup UI, automatic reconnect
- **Standalone**: scheduled jobs, CI/CD, server-side automation, no Chrome required

---

## Security

This extension implements multiple security layers to protect against common attack vectors:

### XSS Prevention
- All dynamic content rendered with `textContent` instead of `innerHTML`
- HTML special characters cannot be injected via progress messages or stage names
- Content Security Policy (CSP) restricts scripts to extension-bundled code only
- CSP blocks inline scripts and external script sources in extension pages
- **Note:** CSP does NOT block Python HTTP requests (native host uses `requests` library, not browser)
- Cross-domain image crawling works because Python bypasses browser CORS/CSP restrictions

### Path Traversal Protection
- Removed `file://` URL scheme from output folder opening
- Uses `chrome.runtime.getURL()` for extension-relative paths only
- Error messages sanitized to strip absolute paths using regex patterns
- Python native host sanitizes exceptions before sending to extension

### Native Messaging Security
- Connection errors handled gracefully without exposing internal state
- Global reconnect timeout prevents infinite reconnect loops (5 minute limit)
- Exponential backoff prevents connection spam (1s → 2s → 4s → 30s max)
- Maximum 10 reconnect attempts before permanent failure

### Error Message Sanitization
- File paths replaced with `<path>` in error messages
- Stack traces stripped of line numbers and file references
- Prevents leakage of internal directory structure to UI

### Data Validation
- Progress payloads validated for expected numeric fields
- Stale detection prevents display of outdated progress (10s threshold)
- RunId tracking ensures status updates match current audit run

### Storage Security
- `chrome.storage.local` used for persistent state (extension sandboxed)
- Status file (`pipeline_status.json`) contains only public progress data
- **Encrypted storage**: AES-GCM encryption for sensitive data (audit secret keys)
- Encryption key derived using PBKDF2 with 100,000 iterations
- Unique initialization vector (IV) per encryption operation

### Command Authentication (HMAC-SHA256)
- **All native messaging commands signed** with HMAC-SHA256 signatures
- Shared secret (256-bit) prevents command forgery
- Secret stored in encrypted storage (extension) and file with 600 permissions (native host)
- Signature verification rejects unsigned or tampered commands
- Prevents malicious processes from impersonating extension or native host

### Domain Whitelist Validation
- **URL domain validation** against hardcoded whitelist with wildcard support
- Allowed domains: `citizensbank.com`, `aprimo.com`, and all subdomains via `*.domain.com` patterns
- Includes Aprimo DAM/CDN domains for embedded images (dam.aprimo.com, r1.previews.aprimo.com, etc.)
- Non-whitelisted URLs rejected with security warnings logged to stderr
- Prevents accidental processing of malicious or unexpected URLs
- Applied to all URL inputs in audit pipeline
- Test whitelist: `python scripts/test_domain_whitelist.py` (19 test cases)

### Setup Security
To enable command authentication:
```powershell
# 1. Generate shared secret
python scripts/generate_audit_secret.py

# 2. Follow output instructions to store secret in encrypted storage
# 3. Reload extension

# Secret is automatically loaded by native host from .audit_secret file
```

### Future Security Enhancements (Optional)
- Rate limiting for reconnect attempts across multiple runs
- Audit logging for security events (failed signatures, rejected URLs)
- Certificate pinning for Aprimo DAM connections
- Sandboxed subprocess execution for Python stages

### Testing Security
To verify security features:
1. **CSP**: Check DevTools console for CSP violations (should be none)
2. **XSS**: Inspect popup HTML to confirm no inline scripts or `innerHTML` usage
3. **Reconnect timeout**: Kill `native_host.py` process (should timeout after 5 min)
4. **Path sanitization**: Check error messages in UI for path leakage (should show `<path>` placeholders)
5. **HMAC signatures**: Try sending unsigned command (should be rejected)
6. **Domain whitelist**: Add non-citizensbank URL to citizensbank_urls.txt (should be rejected)
7. **Encrypted storage**: Check chrome://extensions → Storage → chrome.storage.local (sensitive data should be encrypted with `_enc_` prefix)