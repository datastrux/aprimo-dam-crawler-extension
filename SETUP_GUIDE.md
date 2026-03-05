# Quick Setup Guide - New Machine Installation

## Prerequisites
- Chrome browser installed
- Python 3.8+ installed
- Extension folder copied to new machine

---

## 🚀 Automated Setup (Recommended)

### Windows
```powershell
cd aprimo_dam_crawler_extension
.\setup_new_machine.ps1 -ExtensionId "YOUR_EXTENSION_ID_HERE"
```

### Mac/Linux
```bash
cd aprimo_dam_crawler_extension
chmod +x setup_new_machine.sh
./setup_new_machine.sh --extension-id "YOUR_EXTENSION_ID_HERE"
```

**Getting Extension ID:**
1. Open `chrome://extensions`
2. Enable "Developer mode" (top-right)
3. Click "Load unpacked" → Select extension folder
4. Copy the Extension ID shown

---

## 📋 Manual Setup Steps

### 1. Python Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.\.venv\Scripts\Activate.ps1

# Activate (Mac/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r scripts/requirements-audit.txt
```

### 2. Required Files

**Data Files:**
- `assets/audit/dam_assets.json` - DAM assets export
- `assets/audit/citizensbank_urls.txt` - URLs to crawl

**Secret File:**
```powershell
# Generate audit secret
python scripts/generate_audit_secret.py

# Copy the hex string output
```

### 3. Chrome Extension

**Load Extension:**
1. Open `chrome://extensions`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select extension folder
5. Note the Extension ID

**Store Secret:**
```javascript
// In Chrome DevTools → Service Worker console
const { encryptedStorage } = await import(chrome.runtime.getURL("encrypted_storage.js"));
await encryptedStorage.set({ auditSecretKey: "YOUR_64_CHAR_HEX_HERE" });
```

### 4. Native Messaging
```powershell
# Configure native messaging host
python scripts/install_native_host.py --extension-id "YOUR_EXTENSION_ID"

# Verify installation
python scripts/install_native_host.py --verify --extension-id "YOUR_EXTENSION_ID"
```

### 5. Validation
```powershell
# Run preflight check
python scripts/preflight_check.py

# Expected: ✅ 10/10 checks passed
```

---

## 🧪 Testing

### Test Python Environment
```powershell
python scripts/test_enhancements.py
# Expected: All tests passed
```

### Test Image Fingerprinting (On Machine with Network Access)
```powershell
python scripts/test_known_match.py
# Expected: ✅ ALL TESTS PASSED
```

This test verifies:
- Network access to Citizens Bank and Aprimo preview URLs
- Image download and fingerprinting works correctly
- Perceptual hash matching threshold is appropriate

**Test cases:**
1. Citizens to DAM: Champions in Action logo
2. DAM to DAM duplicates: Bolsover images (phash duplicate detection)

**Note:** This test requires network access to both Citizens Bank website and Aprimo preview server. Run this on the machine where you'll execute the audit pipeline.

### Test Native Messaging
```javascript
// In Chrome DevTools → Service Worker console
chrome.runtime.sendNativeMessage('com.aprimo.dam_audit', 
  {command: 'status'}, 
  response => console.log(response)
);
// Expected: {"status": "ready"} or similar
```

### Test Extension
1. Click extension icon
2. Click "Run Audit Pipeline"
3. Should show: "Audit: running..."

---

## ⚠️ Troubleshooting

### "Native host has exited"
**Fix:** Re-install native host with correct extension ID
```powershell
python scripts/install_native_host.py --extension-id "YOUR_ID"
```

### "Module not found"
**Fix:** Activate venv and reinstall dependencies
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r scripts/requirements-audit.txt
```

### "Invalid HMAC signature"
**Fix:** Regenerate secret and store in extension
```powershell
python scripts/generate_audit_secret.py
# Then store in Chrome as shown above
```

### "Cannot find dam_assets.json"
**Fix:** Copy file to correct location
```powershell
# Must be at: assets/audit/dam_assets.json
```

---

## 📁 Required Directory Structure

```
aprimo_dam_crawler_extension/
├── .venv/                          # Virtual environment
├── .audit_secret                   # Generated secret (64-char hex)
├── assets/
│   └── audit/
│       ├── dam_assets.json         # DAM assets export (required)
│       └── citizensbank_urls.txt   # URLs to crawl (required)
├── reports/                        # Output directory
├── scripts/
│   ├── 01_crawl_citizens_images.py
│   ├── 02_build_dam_fingerprints.py
│   ├── 03_build_citizens_fingerprints.py
│   ├── 04_match_assets.py
│   ├── 05_build_reports.py
│   ├── generate_audit_secret.py
│   ├── install_native_host.py
│   ├── preflight_check.py
│   └── requirements-audit.txt
└── manifest.json
```

---

## ✅ Verification Checklist

- [ ] Python 3.8+ installed and in PATH
- [ ] Virtual environment created and activated
- [ ] All Python dependencies installed
- [ ] dam_assets.json in assets/audit/
- [ ] citizensbank_urls.txt in assets/audit/
- [ ] Audit secret generated and stored in extension
- [ ] Extension loaded in Chrome
- [ ] Native messaging host configured
- [ ] Preflight check passes (10/10)
- [ ] Enhancement tests pass
- [ ] Extension icon clickable
- [ ] "Run Audit Pipeline" button works

---

## 🎯 Quick Commands Reference

```powershell
# Activate venv (always do this first!)
.\.venv\Scripts\Activate.ps1

# Check setup
python scripts/preflight_check.py

# Run audit (CLI)
python scripts/run_audit_standalone.py

# Verify native host
python scripts/install_native_host.py --verify --extension-id "YOUR_ID"

# Test enhancements
python scripts/test_enhancements.py
```

---

## 💡 Tips

1. **Always activate venv** before running Python commands
2. **Use absolute paths** in native host manifest (done automatically by install script)
3. **Reload extension** after changing native host configuration
4. **Check Service Worker console** for detailed error messages
5. **Use CLI mode** if native messaging issues persist:
   ```powershell
   python scripts/run_audit_standalone.py
   ```

---

## 📞 Support

If automated setup fails, follow manual steps above and check:
1. Python version: `python --version` (need 3.8+)
2. Virtual env active: Prompt shows `(.venv)`
3. Dependencies installed: `pip list`
4. Extension ID correct: Check chrome://extensions
5. Native host path: Check manifest at AppData\Local\aprimo_dam_audit\
6. Registry (Windows): HKCU\Software\Google\Chrome\NativeMessagingHosts\com.aprimo.dam_audit

---

**Last Updated:** March 2, 2026
