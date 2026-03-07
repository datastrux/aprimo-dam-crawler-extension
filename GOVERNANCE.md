# Real-Time DAM Governance Features

This branch (`governance/sharepoint`) implements real-time governance monitoring for the DAM audit system.

---

## 🎯 Priority Features Implemented

### ✅ 1. Asset Expiration Monitoring

**Status**: Implemented  
**Update Frequency**: Every 6 hours (configurable)  
**Trigger**: Background alarm in service worker

**How It Works:**
- Chrome extension alarm runs every 6 hours automatically
- Queries current DAM assets from IndexedDB
- Identifies expired and expiring-soon assets (30-day warning)
- Posts report to SharePoint **AssetExpirations** list
- Sends Teams notification if critical expirations found

**Manual Trigger:**
```javascript
// From browser console on DAM page
chrome.runtime.sendMessage({ type: 'GOVERNANCE_CHECK_EXPIRATIONS' });
```

**Configuration:**
- [content.js](content.js#L27-L40) - `EXPIRATION_CONFIG`
- [governance.js](governance.js#L13-L16) - Check interval and alarm settings

---

### ✅ 2. Duplicate Detection (Partial)

**Status**: Infrastructure ready, integration pending  
**Trigger**: When new assets are added during DAM crawl

**How It Works:**
- Detects exact duplicates (SHA256 hash match)
- Detects perceptual duplicates (pHash Hamming distance ≤8)
- Posts to SharePoint **AssetDuplicates** list
- Sends Teams notification for exact matches

**Implementation:**
- [governance.js](governance.js#L233-L313) - Duplicate detection logic
- Hamming distance calculation for pHash comparison
- Confidence scoring (0.0-1.0)

**TODO:**
- Integrate into [content.js](content.js) asset collection flow
- Add duplicate check when `collectAssetCard()` processes new assets
- Store duplicate warnings in asset metadata

---

### ✅ 3. Live Website Compliance Checking

**Status**: Implemented  
**Trigger**: Real-time while browsing citizensbank.com

**How It Works:**
- Auto-collects image URLs while browsing citizensbank.com
- Checks if images use DAM CDN vs local copies
- Identifies compliance issues:
  - **Compliant**: `p1.aprimocdn.net/citizensbank/*` or `www.citizensbank.com/dam/*`
  - **Non-compliant**: Any other citizensbank.com URL
- Stores issues in `chrome.storage.local`
- Posts to SharePoint **ComplianceIssues** list

**Manual Check:**
```javascript
// From browser console on citizensbank.com
const stored = await chrome.storage.local.get('damAudit_autoCollected_v1');
console.log('Compliance issues:', stored.damAudit_autoCollected_v1.complianceIssues);
```

**Configuration:**
- [content.js](content.js#L44-L53) - `AUTO_COLLECTION_CONFIG`
- [governance.js](governance.js#L315-L345) - Compliance checking logic

---

### ✅ 4. Automated Notifications/Workflows

**Status**: Implemented (SharePoint + Teams)  
**Integration Points**:
1. SharePoint REST API (OAuth token required)
2. Teams incoming webhooks (optional)
3. Power Automate flows (manual setup)

**Notification Types:**

| Event | SharePoint List | Teams | Email (via Power Automate) |
|-------|----------------|-------|----------------------------|
| Expired assets found | AssetExpirations | ✅ | Optional |
| Duplicate detected | AssetDuplicates | ✅ (exact match only) | Optional |
| Non-DAM URL detected | ComplianceIssues | Optional | Optional |

**Configuration:**
- [governance.js](governance.js#L23-L33) - SharePoint endpoints and Teams webhook
- [SHAREPOINT_SETUP.md](SHAREPOINT_SETUP.md) - Full setup guide

---

## 📦 Architecture Changes

### New Files

1. **[governance.js](governance.js)** - Governance module
   - SharePoint integration (POST to lists)
   - Teams webhook notifications
   - Expiration monitoring logic
   - Duplicate detection (Hamming distance for pHash)
   - Compliance checking (URL pattern matching)
   - Token management via encrypted storage

2. **[SHAREPOINT_SETUP.md](SHAREPOINT_SETUP.md)** - Setup guide
   - SharePoint Lists schema (3 lists)
   - Azure AD App Registration steps
   - Token generation PowerShell script
   - Power BI dashboard examples
   - Troubleshooting guide

3. **[GOVERNANCE.md](GOVERNANCE.md)** - This file

### Modified Files

1. **[manifest.json](manifest.json)**
   - Added `alarms` permission for periodic monitoring

2. **[content.js](content.js)**
   - Enabled `EXPIRATION_CONFIG` (was disabled)
   - Enabled `AUTO_COLLECTION_CONFIG` with compliance checking
   - Enhanced `autoCollectImageSrcs()` to detect non-DAM URLs
   - Added governance message handler (`GOVERNANCE_CHECK_EXPIRATIONS`)

3. **[worker.js](worker.js)**
   - Import `governance` module
   - Set up expiration monitoring alarm (6-hour interval)
   - Add alarm listener for periodic checks
   - Add governance message handlers

---

## 🚀 Getting Started

### Prerequisites

1. SharePoint site with governance lists ([setup guide](SHAREPOINT_SETUP.md))
2. Azure AD app registration with SharePoint permissions
3. Bearer token for SharePoint REST API

### Setup Steps

1. **Create SharePoint Lists:**
   ```powershell
   # See SHAREPOINT_SETUP.md for full script
   New-PnPList -Title "AssetExpirations" -Template GenericList
   New-PnPList -Title "AssetDuplicates" -Template GenericList
   New-PnPList -Title "ComplianceIssues" -Template GenericList
   ```

2. **Get Access Token:**
   ```powershell
   # See SHAREPOINT_SETUP.md for OAuth2 flow
   $accessToken = Get-SharePointAccessToken -TenantId "..." -ClientId "..." -ClientSecret "..."
   ```

3. **Store Token in Extension:**
   ```javascript
   // In Chrome DevTools console (service worker)
   await storeSharePointToken('YOUR_ACCESS_TOKEN')
   await checkSharePointToken()  // Verify
   ```

4. **Configure Endpoints:**
   - Edit [governance.js](governance.js#L23) with your SharePoint site URLs
   - (Optional) Add Teams webhook URL for instant notifications

5. **Test Features:**
   ```javascript
   // Test expiration monitoring
   chrome.runtime.sendMessage({ type: 'GOVERNANCE_CHECK_EXPIRATIONS' });
   
   // View auto-collected compliance issues
   const stored = await chrome.storage.local.get('damAudit_autoCollected_v1');
   console.log(stored);
   ```

---

## 📊 Governance Metrics

The system tracks these key metrics:

### Expiration Health
- **Expired assets**: Count of assets past expiration date
- **Expiring soon**: Assets expiring within 30 days (configurable)
- **Days expired**: How long each asset has been expired
- **Days remaining**: Time until expiration for warning assets

### Duplicate Detection
- **Exact duplicates**: Pixel-perfect matches (SHA256)
- **Perceptual duplicates**: Visually similar (pHash distance ≤8)
- **Confidence score**: 0.0-1.0 (1.0 = exact match)
- **Duplicate groups**: Sets of 2+ duplicate assets

### Compliance
- **DAM URL adoption**: % of images using DAM CDN
- **Local copies**: Images served from citizensbank.com (non-DAM)
- **Compliance rate**: 1 - (non-compliant / total images)
- **Page coverage**: Pages monitored while browsing

---

## 🔧 Configuration Reference

### Expiration Monitoring

```javascript
// content.js
const EXPIRATION_CONFIG = {
  enabled: true,
  warningDays: 30,  // Alert when expiring within X days
  checkOnStartup: true,
  checkIntervalMinutes: 360,  // 6 hours
  sharepoint: {
    enabled: true,
    notificationList: 'https://...',
    emailRecipients: ['admin@company.com'],
    teamsWebhook: 'https://...',
    authToken: null  // Set via storeSharePointToken()
  }
};
```

### Auto-Collection & Compliance

```javascript
// content.js
const AUTO_COLLECTION_CONFIG = {
  enabled: true,
  collectPageUrls: true,
  collectImageSrcs: true,
  stripQueryParams: true,
  complianceCheck: true,  // NEW: Check DAM URL adoption
  notifyNonCompliance: false  // Log warnings to console
};
```

### Duplicate Detection

```javascript
// governance.js
duplicates: {
  enabled: true,
  phashThreshold: 8,  // Hamming distance (0-64)
  checkOnAssetAdd: true  // TODO: Integrate into crawl flow
}
```

---

## 📈 Next Steps

### Phase 6 Enhancements (Current Branch)

- [ ] Integrate duplicate detection into DAM crawl flow
- [ ] Add visual compliance indicators on citizensbank.com pages
- [ ] Create Python script to sync auto-collected data to SharePoint
- [ ] Add governance summary panel in popup.html

### Phase 7 (Future)

- [ ] Power BI dashboard templates
- [ ] Power Automate flow templates
- [ ] Azure Function for advanced workflows
- [ ] Chrome DevTools panel for governance insights
- [ ] Historical trend tracking (time-series data)

### Phase 8 (Advanced)

- [ ] Machine learning for duplicate detection (image embeddings)
- [ ] Automated asset retirement workflows
- [ ] Content usage analytics (view counts, click tracking)
- [ ] Integration with corporate DAM governance policies

---

## 🛠️ Development

### Running Tests

```javascript
// Test expiration monitoring
chrome.runtime.sendMessage({ type: 'GOVERNANCE_CHECK_EXPIRATIONS' }, console.log);

// Test SharePoint connection
await governance.postToSharePoint(
  governance.config.sharepoint.endpoints.expirations,
  { Title: 'Test Post', ReportDate: new Date().toISOString(), ExpiredCount: 0, ExpiringSoonCount: 0 }
);

// Test Teams notification
await governance.postToTeams({
  '@type': 'MessageCard',
  '@context': 'https://schema.org/extensions',
  summary: 'Test',
  title: 'Test Notification',
  text: 'This is a test from DAM Governance extension'
});
```

### Debugging

**View alarm schedule:**
```javascript
chrome.alarms.getAll(console.log);
```

**View auto-collected data:**
```javascript
const data = await chrome.storage.local.get('damAudit_autoCollected_v1');
console.log('Auto-collected:', data);
```

**Check SharePoint token:**
```javascript
await checkSharePointToken();
```

**View governance config:**
```javascript
import { governance } from './governance.js';
console.log('Config:', governance.config);
```

---

## 📞 Support

### Common Issues

**Q: Expiration alarm not firing?**  
A: Check alarm registration: `chrome.alarms.getAll(console.log)`

**Q: SharePoint POST returns 401?**  
A: Token expired. Re-run `await storeSharePointToken('NEW_TOKEN')`

**Q: Compliance issues not detected?**  
A: Verify `AUTO_COLLECTION_CONFIG.enabled = true` and browse citizensbank.com

**Q: Duplicate detection not working?**  
A: Not yet integrated into crawl flow. Track issue #TBD

### Logs

- **Service worker logs**: Chrome DevTools → Extensions → Service Worker
- **Content script logs**: Browser console (F12) on DAM or citizensbank.com pages
- **SharePoint errors**: Check Network tab for failed POST requests

---

## 📝 License

Same as parent project (Aprimo DAM Crawler Extension)

---

## 🙏 Contributing

This is an internal governance branch. To contribute:

1. Create feature branch from `governance/sharepoint`
2. Implement changes
3. Test with SharePoint sandbox environment
4. Submit PR with governance test results

---

**Last Updated**: March 7, 2026  
**Branch**: governance/sharepoint  
**Status**: Alpha (SharePoint integration ready, duplicate detection pending)
