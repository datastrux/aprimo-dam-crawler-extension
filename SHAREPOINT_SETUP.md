# SharePoint Lists Setup for DAM Governance

This document describes the SharePoint Lists required for real-time DAM governance monitoring.

---

## Prerequisites

1. **SharePoint Site**: Create or use existing site (e.g., `https://company.sharepoint.com/sites/DAM`)
2. **Permissions**: Site Owner or Full Control permissions to create lists
3. **Auth Token**: Azure AD App Registration with SharePoint API permissions

---

## Required SharePoint Lists

### 1. Asset Expirations

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

# Create Asset Expirations list
New-PnPList -Title "AssetExpirations" -Template GenericList
Add-PnPField -List "AssetExpirations" -DisplayName "ReportDate" -InternalName "ReportDate" -Type DateTime -Required
Add-PnPField -List "AssetExpirations" -DisplayName "ExpiredCount" -InternalName "ExpiredCount" -Type Number -Required
Add-PnPField -List "AssetExpirations" -DisplayName "ExpiringSoonCount" -InternalName "ExpiringSoonCount" -Type Number -Required
Add-PnPField -List "AssetExpirations" -DisplayName "ExpiredAssets" -InternalName "ExpiredAssets" -Type Note
Add-PnPField -List "AssetExpirations" -DisplayName "ExpiringSoonAssets" -InternalName "ExpiringSoonAssets" -Type Note

# Create Asset Duplicates list
New-PnPList -Title "AssetDuplicates" -Template GenericList
Add-PnPField -List "AssetDuplicates" -DisplayName "DetectedDate" -InternalName "DetectedDate" -Type DateTime -Required
Add-PnPField -List "AssetDuplicates" -DisplayName "NewAssetId" -InternalName "NewAssetId" -Type Text -Required
Add-PnPField -List "AssetDuplicates" -DisplayName "NewAssetFileName" -InternalName "NewAssetFileName" -Type Text -Required
Add-PnPField -List "AssetDuplicates" -DisplayName "NewAssetUrl" -InternalName "NewAssetUrl" -Type URL
Add-PnPField -List "AssetDuplicates" -DisplayName "DuplicateCount" -InternalName "DuplicateCount" -Type Number -Required
Add-PnPField -List "AssetDuplicates" -DisplayName "DuplicateMatches" -InternalName "DuplicateMatches" -Type Note
Add-PnPField -List "AssetDuplicates" -DisplayName "HighestConfidence" -InternalName "HighestConfidence" -Type Number

# Create Compliance Issues list
New-PnPList -Title "ComplianceIssues" -Template GenericList
Add-PnPField -List "ComplianceIssues" -DisplayName "DetectedDate" -InternalName "DetectedDate" -Type DateTime -Required
Add-PnPField -List "ComplianceIssues" -DisplayName "PageUrl" -InternalName "PageUrl" -Type URL -Required
Add-PnPField -List "ComplianceIssues" -DisplayName "ImageUrl" -InternalName "ImageUrl" -Type URL -Required
Add-PnPField -List "ComplianceIssues" -DisplayName "ImageAlt" -InternalName "ImageAlt" -Type Text
Add-PnPField -List "ComplianceIssues" -DisplayName "Expected" -InternalName "Expected" -Type Text -Required
Add-PnPField -List "ComplianceIssues" -DisplayName "Actual" -InternalName "Actual" -Type Text -Required
Add-PnPField -List "ComplianceIssues" -DisplayName "Severity" -InternalName "Severity" -Type Choice -Choices @("Low","Medium","High") -Required

Write-Host "✅ SharePoint lists created successfully" -ForegroundColor Green
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

Edit [governance.js](governance.js#L16-L33) to set your SharePoint URLs:

```javascript
sharepoint: {
  enabled: true,
  endpoints: {
    expirations: 'https://YOUR_SITE.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'AssetExpirations\')/items',
    duplicates: 'https://YOUR_SITE.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'AssetDuplicates\')/items',
    compliance: 'https://YOUR_SITE.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'ComplianceIssues\')/items'
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
