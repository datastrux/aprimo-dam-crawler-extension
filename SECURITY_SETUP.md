# Security Setup Guide

This guide walks through setting up the security features for the Aprimo DAM Audit Pipeline.

## Overview

The extension now includes production-grade security:
- **HMAC-SHA256 Signature Verification** - Prevents command forgery
- **AES-GCM Encrypted Storage** - Protects sensitive data at rest
- **Domain Whitelist Validation** - Blocks non-approved URLs
- **CSP & XSS Prevention** - Hardens against injection attacks
- **Path Sanitization** - Prevents information leakage

## Quick Setup (5 minutes)

### 1. Generate Shared Secret

```powershell
# Navigate to extension directory
cd C:\Users\colle\Downloads\aprimo_dam_crawler_extension

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Generate secret
python scripts\generate_audit_secret.py
```

**Output:**
```
✅ Secret generated and saved to: C:\Users\...\aprimo_dam_crawler_extension\.audit_secret
📋 Add this to extension's encrypted storage:
{
  "auditSecretKey": "a1b2c3d4..."
}

🔐 Secret (hex): a1b2c3d4e5f6...
```

### 2. Store Secret in Extension

1. Copy the hex secret from output above
2. Open Chrome: `chrome://extensions`
3. Enable **Developer mode** (toggle in top-right)
4. Find "Aprimo DAM Collection Crawler"
5. Click **Service Worker** link (opens DevTools)
6. In Console tab, paste and run:

```javascript
// Import encrypted storage module
const { encryptedStorage } = await import(chrome.runtime.getURL("encrypted_storage.js"));

// Store secret (replace with YOUR secret from step 1)
await encryptedStorage.set({ 
  auditSecretKey: "a1b2c3d4e5f6..." // <- PASTE YOUR SECRET HERE
});

console.log("✅ Secret stored in encrypted storage");
```

### 3. Reload Extension

1. Go back to `chrome://extensions`
2. Click **↻ Reload** button for this extension
3. Verify in Service Worker console:
   ```
   [Worker] HMAC secret loaded from encrypted storage
   ```

### 4. Verify Security

Test that signature verification is working:

```powershell
# Start audit pipeline from extension popup
# Watch for successful signed commands in Service Worker console

# You should see:
# [Worker] HMAC secret loaded from encrypted storage
# (no "Invalid signature" errors)
```

## Security Features Detail

### HMAC Signature Verification

**How it works:**
- Every command sent from extension → native host is signed
- Signature = HMAC-SHA256(command JSON, shared secret)
- Native host verifies signature before processing
- Unsigned or tampered commands are rejected

**Protected against:**
- ✅ Command injection from malicious processes
- ✅ Man-in-the-middle tampering
- ✅ Replay attacks (combined with timestamps)

**Files:**
- Extension secret: Encrypted in `chrome.storage.local` (key: `_enc_auditSecretKey`)
- Native host secret: `.audit_secret` file (permissions: 600 owner-only)

### Encrypted Storage

**How it works:**
- Sensitive data encrypted with AES-GCM before storage
- Encryption key derived from random 256-bit seed using PBKDF2
- 100,000 iterations with SHA-256
- Unique IV (initialization vector) per operation

**Protected against:**
- ✅ Local storage inspection
- ✅ Extension storage dumps
- ✅ Accidental secret exposure in backups

**Files:**
- Implementation: [encrypted_storage.js](encrypted_storage.js)
- Used by: [worker.js](worker.js) for audit secret

### Domain Whitelist

**How it works:**
- All URLs validated against `ALLOWED_DOMAINS` in [audit_common.py](scripts/audit_common.py)
- Only `*.citizensbank.com` domains allowed
- Rejected URLs logged to stderr

**Protected against:**
- ✅ Accidental processing of malicious URLs
- ✅ SSRF (Server-Side Request Forgery) attacks
- ✅ Data exfiltration to external domains

**Files:**
- Validation: [scripts/audit_common.py](scripts/audit_common.py) `validate_url_domain()`
- Whitelist: `ALLOWED_DOMAINS` constant

## Troubleshooting

### "No HMAC secret found" warning

**Problem:** Extension can't find audit secret in encrypted storage

**Solution:**
```javascript
// Check if secret exists
const { encryptedStorage } = await import(chrome.runtime.getURL("encrypted_storage.js"));
const result = await encryptedStorage.get(['auditSecretKey']);
console.log('Secret exists:', !!result.auditSecretKey);

// If false, re-run step 2 above to store secret
```

### "Invalid or missing command signature" error

**Problem:** Extension and native host have different secrets

**Solution:**
```powershell
# 1. Check native host secret exists
ls .audit_secret  # Should show file

# 2. Regenerate and sync secrets
python scripts\generate_audit_secret.py
# Follow output instructions to update extension storage

# 3. Restart native host (stop/start audit from popup)
```

### URLs being rejected as "non-whitelisted"

**Problem:** Valid citizensbank URLs rejected by domain filter

**Solution:**
```python
# Edit scripts/audit_common.py
ALLOWED_DOMAINS = {
    # Citizens Bank domains
    "citizensbank.com",
    "*.citizensbank.com",  # Wildcard for all subdomains
    
    # Aprimo DAM domains (already included)
    "aprimo.com",
    "*.aprimo.com",  # Wildcard for dam., cdn., etc.
    
    # Add custom domains if needed:
    "newcustom.example.com"
}
```

**Note:** Wildcard patterns (`*.domain.com`) match any subdomain:
- `*.aprimo.com` matches `dam.aprimo.com`, `cdn.aprimo.com`, `r1.previews.aprimo.com`
- Also matches the base domain (`aprimo.com`)

## Security Best Practices

### DO ✅
- Keep `.audit_secret` file out of version control (already in .gitignore)
- Regenerate secret if compromised: `python scripts/generate_audit_secret.py`
- Use encrypted storage for any future sensitive data
- Review rejected URLs in stderr logs periodically

### DON'T ❌
- Never commit `.audit_secret` to git
- Never share hex secret in plain text (Slack, email, etc.)
- Never disable signature verification for "convenience"
- Never add non-citizensbank domains to whitelist without security review

## Advanced: Rotating Secrets

If you need to rotate the shared secret:

```powershell
# 1. Generate new secret
python scripts\generate_audit_secret.py

# 2. Update extension (follow output instructions)

# 3. Restart extension
# chrome://extensions → Reload

# 4. Restart native host
# Stop/start audit from popup UI

# Old secret is immediately invalid
```

## Testing Checklist

After setup, verify all security features:

- [ ] HMAC signatures: Check Service Worker console for "HMAC secret loaded"
- [ ] Encrypted storage: Inspect `chrome://extensions` → Storage → chrome.storage.local (should see `_enc_auditSecretKey` with encrypted blob)
- [ ] Domain whitelist: Run `python scripts\test_domain_whitelist.py` (should show 19 passed tests)
- [ ] Domain rejection: Add `http://evil.com/test` to `citizensbank_urls.txt` → run audit → should be rejected
- [ ] CSP: Open popup → check console for CSP violations (should be none)
- [ ] XSS prevention: Inspect popup source → confirm no `innerHTML` usage
- [ ] Path sanitization: Trigger error → check UI message has `<path>` instead of absolute paths

## Questions?

See main [README.md](README.md) Security section for full documentation.
