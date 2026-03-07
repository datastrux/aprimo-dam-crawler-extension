# SharePoint Lists Setup for DAM Governance

This document describes the **5 SharePoint Lists** required for the hybrid data + governance architecture.

---

## Architecture Overview

**Data Layer** (3 lists) - Persistent state, multi-user collaboration:
1. **DAMAssets** - Master catalog of all DAM assets
2. **DiscoveredImages** - Inventory of images found on citizensbank.com
3. **ImageMappings** - Relationships between website images and DAM assets

**Governance Layer** (1 list) - Events, monitoring, alerts:
4. **GovernanceEvents** - Unified event log for expirations, duplicates, compliance issues

**Legacy** (removed):
- ~~AssetExpirations~~ → Now `GovernanceEvents` with `EventType='ExpirationReport'`
- ~~AssetDuplicates~~ → Now `GovernanceEvents` with `EventType='DuplicateDetected'`
- ~~ComplianceIssues~~ → Now `GovernanceEvents` with `EventType='ComplianceViolation'`

---

## Prerequisites

1. **SharePoint Site**: Create or use existing site (e.g., `https://company.sharepoint.com/sites/DAM`)
2. **Permissions**: Site Owner or Full Control permissions to create lists
3. **Auth Token**: Azure AD App Registration with SharePoint API permissions

---

## Required SharePoint Lists

### Data Layer

### 1. DAMAssets

**List Name**: `DAMAssets`  
**Purpose**: Master catalog of all Aprimo DAM assets (10,455+ assets)  
**Update Frequency**: Daily sync from dam_assets.json

#### Columns

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| Title | Single line text | Yes | File name (user-friendly display) |
| AssetID | Single line text | Yes | Aprimo item ID (unique key) |
| FileName | Single line text | Yes | Original file name |
| PreviewURL | Hyperlink | No | Preview image URL |
| ExpirationDate | Date & Time | No | Asset expiration date |
| Status | Choice | Yes | Active, Expiring Soon, Expired |
| SHA256 | Single line text | No | SHA256 hash for exact matching |
| pHash | Single line text | No | Perceptual hash for duplicate detection |
| FileType | Single line text | No | jpg, png, etc. |
| LastSyncedFromAprimo | Date & Time | Yes | When last updated from DAM |

#### Choice Values for Status
- Active
- Expiring Soon (within 30 days)
- Expired

#### Sample Data

```json
{
  "Title": "hero_homepage_2026.jpg",
  "AssetID": "abc123xyz",
  "FileName": "hero_homepage_2026.jpg",
  "PreviewURL": "https://r1.previews.aprimo.com/...",
  "ExpirationDate": "2026-12-31T00:00:00Z",
  "Status": "Active",
  "SHA256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "pHash": "f8d8c8c8a8a8c8c8",
  "FileType": "jpg",
  "LastSyncedFromAprimo": "2026-03-07T08:00:00Z"
}
```

---

### 2. DiscoveredImages

**List Name**: `DiscoveredImages`  
**Purpose**: Inventory of all images discovered on citizensbank.com  
**Update Frequency**: Real-time as users browse (auto-collection)

#### Columns

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| Title | Single line text | Yes | Image URL (display) |
| ImageURL | Hyperlink | Yes | Full URL of the image |
| PageURL | Hyperlink | Yes | Page where image was found |
| DiscoveredBy | Person or Group | No | Extension user who discovered it |
| FirstSeen | Date & Time | Yes | When first discovered |
| LastSeen | Date & Time | Yes | Most recent sighting |
| Status | Choice | Yes | Active, Broken, Removed |
| ImageAlt | Multiple lines text | No | Alt text for context |

#### Choice Values for Status
- Active
- Broken (404/403 errors)
- Removed (not seen in 90 days)

#### Sample Data

```json
{
  "Title": "https://www.citizensbank.com/images/hero.jpg",
  "ImageURL": "https://www.citizensbank.com/images/hero.jpg",
  "PageURL": "https://www.citizensbank.com/personal-banking",
  "DiscoveredBy": "Web Team User",
  "FirstSeen": "2026-02-15T14:22:00Z",
  "LastSeen": "2026-03-07T10:15:00Z",
  "Status": "Active",
  "ImageAlt": "Personal Banking Hero"
}
```

---

### 3. ImageMappings

**List Name**: `ImageMappings`  
**Purpose**: Relationships between citizensbank.com images and DAM assets  
**Update Frequency**: Created when matches are found

#### Columns

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| Title | Single line text | Yes | Auto-generated summary |
| CitizensBankImageURL | Hyperlink | Yes | URL from DiscoveredImages |
| DAMAssetID | Single line text | Yes | AssetID from DAMAssets list |
| MatchConfidence | Number | Yes | 0-100 confidence score |
| MatchMethod | Choice | Yes | SHA256, pHash, Manual |
| IsDuplicate | Yes/No | No | Marks duplicate usage patterns |
| LastVerified | Date & Time | Yes | When mapping was confirmed |

#### Choice Values for MatchMethod
- SHA256 (exact pixel match)
- pHash (perceptual/visual similarity)
- Manual (user-verified)

#### Sample Data

```json
{
  "Title": "www.citizensbank.com/images/hero.jpg → abc123xyz",
  "CitizensBankImageURL": "https://www.citizensbank.com/images/hero.jpg",
  "DAMAssetID": "abc123xyz",
  "MatchConfidence": 100,
  "MatchMethod": "SHA256",
  "IsDuplicate": false,
  "LastVerified": "2026-03-07T11:00:00Z"
}
```

---

### Governance Layer

### 4. GovernanceEvents

**List Name**: `GovernanceEvents`  
**Purpose**: Unified event log for all governance monitoring (expirations, duplicates, compliance)  
**Update Frequency**: Real-time event-driven

#### Columns

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| Title | Single line text | Yes | Event summary |
| EventType | Choice | Yes | ExpirationReport, DuplicateDetected, ComplianceViolation |
| EventDate | Date & Time | Yes | When event occurred |
| EventData | Multiple lines text | Yes | JSON details specific to event type |
| Severity | Choice | Yes | Low, Medium, High, Critical |
| NotificationSent | Yes/No | Yes | Whether Teams/email was sent |
| AssignedTo | Person or Group | No | Task owner (for actionable events) |
| Status | Choice | Yes | New, InProgress, Resolved |

#### Choice Values for EventType
- ExpirationReport
- DuplicateDetected
- ComplianceViolation
- BrokenImage (future)
- UnmatchedImage (future)

#### Choice Values for Severity
- Low
- Medium
- High
- Critical

#### Choice Values for Status
- New
- InProgress
- Resolved

#### Sample Data

**Expiration Report:**
```json
{
  "Title": "Asset Expiration Report - 5 expired, 12 expiring soon",
  "EventType": "ExpirationReport",
  "EventDate": "2026-03-07T14:00:00Z",
  "EventData": "{\"expiredCount\":5,\"expiringSoonCount\":12,\"expired\":[{\"itemId\":\"abc123\",\"fileName\":\"promo_2025.jpg\",\"daysExpired\":15}],\"expiringSoon\":[...]}",
  "Severity": "High",
  "NotificationSent": true,
  "AssignedTo": "DAM Admin",
  "Status": "New"
}
```

**Duplicate Detection:**
```json
{
  "Title": "Duplicate Detected: hero_homepage_2026.jpg",
  "EventType": "DuplicateDetected",
  "EventDate": "2026-03-07T09:30:00Z",
  "EventData": "{\"newAssetId\":\"xyz789\",\"duplicateCount\":2,\"highestConfidence\":1.0,\"duplicateMatches\":[{\"type\":\"exact\",\"itemId\":\"abc123\"}]}",
  "Severity": "High",
  "NotificationSent": true,
  "AssignedTo": "Content Team",
  "Status": "InProgress"
}
```

**Compliance Violation:**
```json
{
  "Title": "Non-DAM URL Detected: www.citizensbank.com/personal-banking",
  "EventType": "ComplianceViolation",
  "EventDate": "2026-03-07T11:45:00Z",
  "EventData": "{\"pageUrl\":\"https://www.citizensbank.com/personal-banking\",\"imageUrl\":\"https://www.citizensbank.com/images/hero.jpg\",\"expected\":\"DAM CDN URL\",\"actual\":\"Local copy\"}",
  "Severity": "Medium",
  "NotificationSent": false,
  "AssignedTo": "Web Team",
  "Status": "New"
}
```

#### Power Automate Flow (Optional)

**Trigger**: When item is created  
**Conditions**:
- If `EventType = 'ExpirationReport'` AND `Severity = 'High'` → Email DAM admin
- If `EventType = 'DuplicateDetected'` AND `Severity = 'High'` → Post to Teams
- If `EventType = 'ComplianceViolation'` AND `Severity >= 'Medium'` → Assign to web team

---

## Removed Lists (Now Consolidated)

The following lists from the original 3-list design have been consolidated into `GovernanceEvents`:

### ~~1. Asset Expirations~~ → `GovernanceEvents` with `EventType='ExpirationReport'`

**List Name**: `AssetExpirations`  
**Purpose**: Track expired and expiring DAM assets  
**Update Frequency**: Every 6 hours (configurable)

#### Columns

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| Title | Single line text | Yes | Report title (auto-generated) |
| ReportDate | Date & Time | Yes | When the check was run |
| ExpiredCount | Number | Yes | Number of expired assets |
| ExpiringSoonCount | Number | Yes | Number of assets expiring within 30 days |
| ExpiredAssets | Multiple lines text | No | JSON array of expired asset details |
| ExpiringSoonAssets | Multiple lines text | No | JSON array of expiring assets |

#### Sample Data

```json
{
  "Title": "Asset Expiration Report - 2026-03-07T14:30:00Z",
  "ReportDate": "2026-03-07T14:30:00Z",
  "ExpiredCount": 5,
  "ExpiringSoonCount": 12,
  "ExpiredAssets": "[{\"itemId\":\"abc123\",\"fileName\":\"promo_2025.jpg\",\"daysExpired\":15}]",
  "ExpiringSoonAssets": "[{\"itemId\":\"def456\",\"fileName\":\"banner_spring.jpg\",\"daysRemaining\":10}]"
}
```

#### Power Automate Flow (Optional)

**Trigger**: When item is created  
**Actions**:
1. Parse JSON from ExpiredAssets field
2. For each expired asset:
   - Send email to DAM admin
   - Create task in Planner
3. Post summary to Teams channel

---

### 2. Asset Duplicates

**List Name**: `AssetDuplicates`  
**Purpose**: Track duplicate assets detected in DAM  
**Update Frequency**: Real-time (when duplicate detected during crawl)

#### Columns

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| Title | Single line text | Yes | Duplicate detection summary |
| DetectedDate | Date & Time | Yes | When duplicate was detected |
| NewAssetId | Single line text | Yes | Item ID of newly added asset |
| NewAssetFileName | Single line text | Yes | Filename of new asset |
| NewAssetUrl | Hyperlink | No | Link to asset in DAM |
| DuplicateCount | Number | Yes | Number of duplicate matches found |
| DuplicateMatches | Multiple lines text | No | JSON array of duplicate details |
| HighestConfidence | Number | No | Confidence score (0.0-1.0) |

#### Sample Data

```json
{
  "Title": "Duplicate Detected: hero_homepage_2026.jpg",
  "DetectedDate": "2026-03-07T09:15:00Z",
  "NewAssetId": "xyz789",
  "NewAssetFileName": "hero_homepage_2026.jpg",
  "NewAssetUrl": "https://dam.aprimo.com/items/xyz789",
  "DuplicateCount": 2,
  "DuplicateMatches": "[{\"type\":\"exact\",\"matchedAsset\":{\"itemId\":\"abc123\",\"fileName\":\"hero_2026.jpg\"},\"confidence\":1.0}]",
  "HighestConfidence": 1.0
}
```

#### Power Automate Flow (Optional)

**Trigger**: When item is created  
**Condition**: HighestConfidence >= 0.95 (exact or near-exact duplicate)  
**Actions**:
1. Send Teams notification to DAM governance channel
2. Create approval workflow for content owner
3. If approved: archive older duplicate

---

### 3. Compliance Issues

**List Name**: `ComplianceIssues`  
**Purpose**: Track non-DAM URLs found on citizensbank.com  
**Update Frequency**: Real-time (during browsing with auto-collection enabled)

#### Columns

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| Title | Single line text | Yes | Issue summary |
| DetectedDate | Date & Time | Yes | When issue was detected |
| PageUrl | Hyperlink | Yes | Page where non-compliant image found |
| ImageUrl | Hyperlink | Yes | URL of the non-DAM image |
| ImageAlt | Single line text | No | Alt text for context |
| Expected | Single line text | Yes | Expected pattern (e.g., "DAM CDN URL") |
| Actual | Single line text | Yes | Actual pattern (e.g., "Local copy") |
| Severity | Choice | Yes | Low, Medium, High |

#### Choice Values for Severity

- Low: Placeholder/icon images
- Medium: Content images (most cases)
- High: Hero images, critical assets

#### Sample Data

```json
{
  "Title": "Non-DAM URL Detected",
  "DetectedDate": "2026-03-07T11:22:00Z",
  "PageUrl": "https://www.citizensbank.com/personal-banking",
  "ImageUrl": "https://www.citizensbank.com/images/hero_personal_banking.jpg",
  "ImageAlt": "Personal Banking Hero",
  "Expected": "DAM CDN URL",
  "Actual": "Local copy",
  "Severity": "High"
}
```

#### Power Automate Flow (Optional)

**Trigger**: When item is created  
**Condition**: Severity = "High"  
**Actions**:
1. Send email to web team
2. Create work item in Azure DevOps
3. Post to Teams governance channel

---

## Setup Instructions

### Step 1: Create Lists in SharePoint

1. Navigate to your SharePoint site (e.g., `https://company.sharepoint.com/sites/DAM`)
2. Click **Site contents** → **New** → **List**
3. Create each list with the columns defined above

**PowerShell Script** (requires PnP PowerShell):

```powershell
# Install PnP PowerShell if not already installed
# Install-Module -Name PnP.PowerShell -Scope CurrentUser

# Connect to SharePoint site
Connect-PnPOnline -Url "https://company.sharepoint.com/sites/DAM" -Interactive

Write-Host "`n=== Creating Data Layer Lists ===" -ForegroundColor Cyan

# List 1: DAMAssets (Master catalog)
Write-Host "`nCreating DAMAssets list..." -ForegroundColor Yellow
New-PnPList -Title "DAMAssets" -Template GenericList
Add-PnPField -List "DAMAssets" -DisplayName "AssetID" -InternalName "AssetID" -Type Text -Required
Add-PnPField -List "DAMAssets" -DisplayName "FileName" -InternalName "FileName" -Type Text -Required
Add-PnPField -List "DAMAssets" -DisplayName "PreviewURL" -InternalName "PreviewURL" -Type URL
Add-PnPField -List "DAMAssets" -DisplayName "ExpirationDate" -InternalName "ExpirationDate" -Type DateTime
Add-PnPField -List "DAMAssets" -DisplayName "Status" -InternalName "Status" -Type Choice -Choices @("Active","Expiring Soon","Expired") -Required
Add-PnPField -List "DAMAssets" -DisplayName "SHA256" -InternalName "SHA256" -Type Text
Add-PnPField -List "DAMAssets" -DisplayName "pHash" -InternalName "pHash" -Type Text
Add-PnPField -List "DAMAssets" -DisplayName "FileType" -InternalName "FileType" -Type Text
Add-PnPField -List "DAMAssets" -DisplayName "LastSyncedFromAprimo" -InternalName "LastSyncedFromAprimo" -Type DateTime -Required
Write-Host "✅ DAMAssets created" -ForegroundColor Green

# List 2: DiscoveredImages (Website inventory)
Write-Host "`nCreating DiscoveredImages list..." -ForegroundColor Yellow
New-PnPList -Title "DiscoveredImages" -Template GenericList
Add-PnPField -List "DiscoveredImages" -DisplayName "ImageURL" -InternalName "ImageURL" -Type URL -Required
Add-PnPField -List "DiscoveredImages" -DisplayName "PageURL" -InternalName "PageURL" -Type URL -Required
Add-PnPField -List "DiscoveredImages" -DisplayName "DiscoveredBy" -InternalName "DiscoveredBy" -Type User
Add-PnPField -List "DiscoveredImages" -DisplayName "FirstSeen" -InternalName "FirstSeen" -Type DateTime -Required
Add-PnPField -List "DiscoveredImages" -DisplayName "LastSeen" -InternalName "LastSeen" -Type DateTime -Required
Add-PnPField -List "DiscoveredImages" -DisplayName "Status" -InternalName "Status" -Type Choice -Choices @("Active","Broken","Removed") -Required
Add-PnPField -List "DiscoveredImages" -DisplayName "ImageAlt" -InternalName "ImageAlt" -Type Note
Write-Host "✅ DiscoveredImages created" -ForegroundColor Green

# List 3: ImageMappings (Relationships)
Write-Host "`nCreating ImageMappings list..." -ForegroundColor Yellow
New-PnPList -Title "ImageMappings" -Template GenericList
Add-PnPField -List "ImageMappings" -DisplayName "CitizensBankImageURL" -InternalName "CitizensBankImageURL" -Type URL -Required
Add-PnPField -List "ImageMappings" -DisplayName "DAMAssetID" -InternalName "DAMAssetID" -Type Text -Required
Add-PnPField -List "ImageMappings" -DisplayName "MatchConfidence" -InternalName "MatchConfidence" -Type Number -Required
Add-PnPField -List "ImageMappings" -DisplayName "MatchMethod" -InternalName "MatchMethod" -Type Choice -Choices @("SHA256","pHash","Manual") -Required
Add-PnPField -List "ImageMappings" -DisplayName "IsDuplicate" -InternalName "IsDuplicate" -Type Boolean
Add-PnPField -List "ImageMappings" -DisplayName "LastVerified" -InternalName "LastVerified" -Type DateTime -Required
Write-Host "✅ ImageMappings created" -ForegroundColor Green

Write-Host "`n=== Creating Governance Layer Lists ===" -ForegroundColor Cyan

# List 4: GovernanceEvents (Unified event log)
Write-Host "`nCreating GovernanceEvents list..." -ForegroundColor Yellow
New-PnPList -Title "GovernanceEvents" -Template GenericList
Add-PnPField -List "GovernanceEvents" -DisplayName "EventType" -InternalName "EventType" -Type Choice -Choices @("ExpirationReport","DuplicateDetected","ComplianceViolation","BrokenImage","UnmatchedImage") -Required
Add-PnPField -List "GovernanceEvents" -DisplayName "EventDate" -InternalName "EventDate" -Type DateTime -Required
Add-PnPField -List "GovernanceEvents" -DisplayName "EventData" -InternalName "EventData" -Type Note -Required
Add-PnPField -List "GovernanceEvents" -DisplayName "Severity" -InternalName "Severity" -Type Choice -Choices @("Low","Medium","High","Critical") -Required
Add-PnPField -List "GovernanceEvents" -DisplayName "NotificationSent" -InternalName "NotificationSent" -Type Boolean -Required
Add-PnPField -List "GovernanceEvents" -DisplayName "AssignedTo" -InternalName "AssignedTo" -Type User
Add-PnPField -List "GovernanceEvents" -DisplayName "Status" -InternalName "Status" -Type Choice -Choices @("New","InProgress","Resolved") -Required
Write-Host "✅ GovernanceEvents created" -ForegroundColor Green

Write-Host "`n✅ All 5 SharePoint lists created successfully!" -ForegroundColor Green
Write-Host "   - DAMAssets (Data)" -ForegroundColor White
Write-Host "   - DiscoveredImages (Data)" -ForegroundColor White
Write-Host "   - ImageMappings (Data)" -ForegroundColor White
Write-Host "   - GovernanceEvents (Governance)" -ForegroundColor White
```

### Step 2: Configure Azure AD App Registration

1. Go to **Azure Portal** → **Azure Active Directory** → **App registrations**
2. Click **New registration**
   - Name: `DAM Governance Extension`
   - Supported account types: Single tenant
   - Redirect URI: Not needed for service account
3. Click **Register**
4. Note the **Application (client) ID**
5. Go to **API permissions** → **Add a permission**
   - Select **SharePoint**
   - Select **Application permissions**
   - Add `Sites.ReadWrite.All`
6. Click **Grant admin consent**
7. Go to **Certificates & secrets** → **New client secret**
   - Description: `DAM Extension`
   - Expires: 24 months (or as per policy)
8. **Copy the secret value** (you won't see it again)

### Step 3: Get Access Token

Use this PowerShell script to get a Bearer token:

```powershell
# Azure AD App details
$tenantId = "YOUR_TENANT_ID"
$clientId = "YOUR_CLIENT_ID"
$clientSecret = "YOUR_CLIENT_SECRET"
$resource = "https://company.sharepoint.com"

# Get token
$tokenUrl = "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token"
$body = @{
    client_id = $clientId
    scope = "$resource/.default"
    client_secret = $clientSecret
    grant_type = "client_credentials"
}

$response = Invoke-RestMethod -Method Post -Uri $tokenUrl -Body $body
$accessToken = $response.access_token

Write-Host "✅ Access Token:" -ForegroundColor Green
Write-Host $accessToken

# Test token by listing SharePoint sites
$testUrl = "$resource/_api/web/lists/getbytitle('AssetExpirations')/items"
$headers = @{
    "Authorization" = "Bearer $accessToken"
    "Accept" = "application/json;odata=verbose"
}

try {
    $testResponse = Invoke-RestMethod -Method Get -Uri $testUrl -Headers $headers
    Write-Host "✅ Token is valid and can access SharePoint" -ForegroundColor Green
} catch {
    Write-Host "❌ Token test failed: $_" -ForegroundColor Red
}
```

### Step 4: Configure Extension

1. Open Chrome and load the extension
2. Click extension icon → **Service Worker** (opens DevTools)
3. In Console, store the SharePoint token:

```javascript
await storeSharePointToken('YOUR_ACCESS_TOKEN_HERE')
```

4. Verify it's stored:

```javascript
await checkSharePointToken()
```

**Expected output:**
```
✅ SharePoint token is configured
Token (first 20 chars): eyJ0eXAiOiJKV1QiLCJ...
```

### Step 5: Update Governance Configuration

Edit [governance.js](governance.js#L36-L54) to set your SharePoint URLs:

```javascript
sharepoint: {
  enabled: true,
  authTokenKey: 'sharepointAuthToken',
  siteUrl: 'https://YOUR_SITE.sharepoint.com/sites/DAM',
  endpoints: {
    // Data Layer
    damAssets: 'https://YOUR_SITE.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'DAMAssets\')/items',
    discoveredImages: 'https://YOUR_SITE.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'DiscoveredImages\')/items',
    imageMappings: 'https://YOUR_SITE.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'ImageMappings\')/items',
    
    // Governance Layer
    governanceEvents: 'https://YOUR_SITE.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'GovernanceEvents\')/items'
  },
  teamsWebhook: 'https://YOUR_TENANT.webhook.office.com/webhookb2/YOUR_WEBHOOK_ID'  // Optional
}
```

---

## Testing

### Test Expiration Monitoring

1. Navigate to Aprimo DAM page with the extension enabled
2. Open browser console (F12)
3. Trigger manual check:

```javascript
chrome.runtime.sendMessage({ type: 'GOVERNANCE_CHECK_EXPIRATIONS' }, (response) => {
  console.log('Expiration check result:', response);
});
```

4. Verify item created in SharePoint **AssetExpirations** list

### Test Duplicate Detection

1. Add an asset to DAM that duplicates an existing asset
2. Crawl the collection containing both assets
3. Check SharePoint **AssetDuplicates** list for new entry

### Test Compliance Checking

1. Browse to `https://www.citizensbank.com` with extension enabled
2. Open console and verify auto-collection is running
3. Check SharePoint **ComplianceIssues** list for non-DAM URLs

---

## Power BI Dashboard (Optional)

### Connect Power BI to SharePoint Lists

1. Open Power BI Desktop
2. Get Data → **SharePoint Online List**
3. Enter site URL: `https://company.sharepoint.com/sites/DAM`
4. Select all three lists
5. Click **Load**

### Sample Measures

```dax
// Total Expired Assets
Total Expired = SUM(AssetExpirations[ExpiredCount])

// Compliance Rate
Compliance Rate = 
VAR TotalImages = COUNTROWS(ComplianceIssues) + [DAM Images Count]
VAR NonCompliant = COUNTROWS(ComplianceIssues)
RETURN 1 - DIVIDE(NonCompliant, TotalImages, 0)

// Duplicate Detection Rate
Duplicate Rate = 
DIVIDE(
    SUM(AssetDuplicates[DuplicateCount]), 
    [Total DAM Assets], 
    0
)
```

### Suggested Visualizations

1. **Card**: Total expired assets (red alert if > 0)
2. **Line chart**: Compliance rate trend over time
3. **Table**: Recent compliance issues with PageUrl and ImageUrl
4. **Bar chart**: Duplicates by confidence level
5. **Gauge**: Overall governance score (0-100)

---

## Troubleshooting

### SharePoint POST returns 401 Unauthorized

- **Cause**: Token expired or invalid
- **Fix**: Generate new token and run `await storeSharePointToken('NEW_TOKEN')`

### SharePoint POST returns 403 Forbidden

- **Cause**: App doesn't have write permissions
- **Fix**: Re-grant `Sites.ReadWrite.All` permission in Azure AD

### No expirations detected despite expired assets

- **Cause**: Expiration date format not recognized
- **Fix**: Check `expirationDate` field format (should be ISO 8601: `2026-03-07T00:00:00Z`)

### Compliance issues not posting to SharePoint

- **Cause**: Auto-collection disabled
- **Fix**: Verify `AUTO_COLLECTION_CONFIG.enabled = true` in [content.js](content.js#L44)

---

## Security Best Practices

1. **Rotate tokens regularly**: Set client secrets to expire every 6-12 months
2. **Use separate service accounts**: Don't use personal accounts for automation
3. **Limit permissions**: Only grant `Sites.ReadWrite.All`, not `Sites.FullControl.All`
4. **Monitor token usage**: Set up Azure AD sign-in logs alerts
5. **Encrypt tokens at rest**: Extension uses AES-GCM encryption via `encrypted_storage.js`

---

## Next Steps

1. Set up Power Automate flows for notifications
2. Create Power BI governance dashboard
3. Schedule weekly governance reports
4. Define escalation policies for critical issues
5. Train content team on compliance requirements
