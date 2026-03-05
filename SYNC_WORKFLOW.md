# Machine Synchronization Workflow

## Syncing Code Changes Between Machines

### On Machine 1 (Development Machine - This Machine)

```powershell
# 1. Commit any changes
git add -A
git commit -m "Your commit message"

# 2. Push to remote
git push origin main

# 3. Verify push succeeded
git log -1 --oneline
```

### On Machine 2 (Execution Machine - Has Network Access)

```powershell
# Navigate to project directory
cd path\to\aprimo_dam_crawler_extension

# Pull latest changes
git pull origin main

# Verify you have latest commit
git log -1 --oneline

# Reload extension in Chrome
# Go to chrome://extensions, find "DAM Audit Pipeline", click reload icon
```

---

## Running Pipeline on Machine 2

### Before Running
```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Verify network access and fingerprinting works
python scripts/test_known_match.py
```

### Run Full Pipeline
1. Open Chrome extension popup
2. **Important**: Set phash threshold if needed (default: 8)
3. Click "Run Full Pipeline"
4. Wait for completion (monitor progress in popup)

### Generated Files
```
assets/audit/
  ├── dam_assets.json              (already committed)
  ├── citizensbank_urls.txt        (already committed)
  ├── citizens_images.json         (NEW - generated)
  ├── dam_fingerprints.json        (NEW - generated)
  ├── citizens_fingerprints.json   (NEW - generated)
  ├── match_results.json           (NEW - generated)
  ├── unmatched_results.json       (NEW - generated)
  ├── dam_internal_dupes.json      (NEW - generated)
  ├── dam_phash_dupes.json         (NEW - generated)
  ├── citizens_duplicates.json     (NEW - generated)
  └── governance_metrics.json      (NEW - generated)

reports/
  ├── citizens_dam_audit.xlsx      (NEW - Excel report)
  └── audit_report.html            (NEW - HTML dashboard)
```

---

## Syncing Results BACK to Machine 1

### Option 1: Git (Recommended for Small Reports)
```powershell
# On Machine 2 - Commit and push reports
git add assets/audit/*.json reports/*
git commit -m "feat: Add audit results - $(Get-Date -Format 'yyyy-MM-dd')"
git push origin main

# On Machine 1 - Pull reports
git pull origin main

# View reports locally
# Open Chrome: chrome-extension://YOUR_EXTENSION_ID/reports/audit_report.html
```

### Option 2: Network Share (For Large Files)
```powershell
# On Machine 2 - Copy to network share
$reportDate = Get-Date -Format "yyyy-MM-dd_HH-mm"
$destFolder = "\\network-share\audit-reports\$reportDate"
New-Item -ItemType Directory -Path $destFolder -Force
Copy-Item -Path "reports\*" -Destination $destFolder -Recurse
Copy-Item -Path "assets\audit\*.json" -Destination "$destFolder\audit-data" -Recurse

# On Machine 1 - Copy from network share
Copy-Item -Path "\\network-share\audit-reports\$reportDate\*" -Destination "reports\" -Recurse
Copy-Item -Path "\\network-share\audit-reports\$reportDate\audit-data\*" -Destination "assets\audit\" -Recurse
```

### Option 3: Cloud Storage (OneDrive/Dropbox)
```powershell
# On Machine 2 - Copy to cloud folder
$cloudFolder = "$env:USERPROFILE\OneDrive\AuditReports\$(Get-Date -Format 'yyyy-MM-dd_HH-mm')"
New-Item -ItemType Directory -Path $cloudFolder -Force
Copy-Item -Path "reports\*" -Destination $cloudFolder -Recurse
Copy-Item -Path "assets\audit\*.json" -Destination "$cloudFolder\audit-data" -Recurse

# On Machine 1 - Wait for sync, then copy from cloud folder
# (Cloud service syncs automatically)
Copy-Item -Path "$env:USERPROFILE\OneDrive\AuditReports\LATEST\*" -Destination "reports\" -Recurse
```

### Option 4: USB Drive
```powershell
# On Machine 2 - Copy to USB
$usbDrive = "E:"  # Adjust drive letter
$reportFolder = "$usbDrive\audit-$(Get-Date -Format 'yyyy-MM-dd')"
New-Item -ItemType Directory -Path $reportFolder -Force
Copy-Item -Path "reports\*" -Destination $reportFolder -Recurse
Copy-Item -Path "assets\audit\*.json" -Destination "$reportFolder\audit-data" -Recurse

# On Machine 1 - Copy from USB
$usbDrive = "E:"  # Adjust drive letter
Copy-Item -Path "$usbDrive\audit-LATEST\*" -Destination "reports\" -Recurse
Copy-Item -Path "$usbDrive\audit-LATEST\audit-data\*" -Destination "assets\audit\" -Recurse
```

---

## Viewing Reports After Sync

### Method 1: Extension (Recommended)
1. Load extension in Chrome
2. Click extension icon
3. Click "📂 View Reports" button
4. Opens `reports/audit_report.html` directly

### Method 2: File System
```powershell
# Open HTML report
Start-Process "chrome.exe" "$(pwd)\reports\audit_report.html"

# Open Excel report
Start-Process "$(pwd)\reports\citizens_dam_audit.xlsx"
```

### Method 3: Live Preview (VS Code)
1. Install "Live Preview" extension in VS Code
2. Right-click `reports/audit_report.html`
3. Select "Show Preview"

---

## Recommended Workflow

### Weekly Audit Cycle
```powershell
# Machine 1 - Send latest code
git push origin main

# Machine 2 - Get code and run
git pull origin main
python scripts/test_known_match.py  # Verify
# Run pipeline via extension UI
git add assets/audit/*.json reports/*
git commit -m "audit: Results for week of $(Get-Date -Format 'yyyy-MM-dd')"
git push origin main

# Machine 1 - Get results
git pull origin main
# View reports via extension
```

---

## Troubleshooting

### Git Push Fails (File Too Large)
```powershell
# Check file sizes
Get-ChildItem -Recurse | Where-Object {$_.Length -gt 50MB} | Select-Object FullName, @{Name="SizeMB";Expression={[math]::Round($_.Length/1MB,2)}}

# If reports are too large, use Option 2, 3, or 4 above
```

### Extension Not Showing Latest Code
```powershell
# Hard reload extension
# 1. Go to chrome://extensions
# 2. Toggle extension OFF then ON
# 3. Click reload icon
```

### Reports Not Loading
```powershell
# Verify files exist
Test-Path "reports\audit_report.html"
Test-Path "reports\citizens_dam_audit.xlsx"

# Check file permissions
Get-Acl "reports\audit_report.html" | Format-List
```

---

## File Size Management

### Check Repository Size
```powershell
git count-objects -vH
```

### Current File Sizes
```powershell
# Check audit data sizes
Get-ChildItem "assets\audit\*.json" | Select-Object Name, @{Name="SizeMB";Expression={[math]::Round($_.Length/1MB,2)}}

# Check report sizes  
Get-ChildItem "reports\*" | Select-Object Name, @{Name="SizeMB";Expression={[math]::Round($_.Length/1MB,2)}}
```

### If Git Becomes Too Large
```powershell
# Add large files to .gitignore
Add-Content .gitignore "`nreports/*.xlsx`nreports/*.html"

# Use alternative sync method (network/cloud/USB) for reports only
```
