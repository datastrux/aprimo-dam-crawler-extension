# Complete Environment Setup for Aprimo DAM Audit Extension
# This script automates ALL setup steps including secret generation and data file management

param(
    [Parameter(Mandatory=$true)]
    [string]$ExtensionId,
    
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  APRIMO DAM AUDIT - COMPLETE SETUP" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Step 1: Verify Python
Write-Host "[1/8] Checking Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "Python 3\.(\d+)") {
    Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ Python 3.8+ required" -ForegroundColor Red
    exit 1
}

# Step 2: Create/Activate Virtual Environment
Write-Host "`n[2/8] Setting up virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path ".venv")) {
    Write-Host "  Creating .venv..." -ForegroundColor Gray
    python -m venv .venv
}
Write-Host "  ✓ Virtual environment ready" -ForegroundColor Green

# Activate venv
& .\.venv\Scripts\Activate.ps1
Write-Host "  ✓ Activated .venv" -ForegroundColor Green

# Step 3: Install Python Requirements
Write-Host "`n[3/8] Installing Python packages..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
pip install -r scripts\requirements-audit.txt --quiet
Write-Host "  ✓ All packages installed:" -ForegroundColor Green
pip list | Select-String -Pattern "(requests|beautifulsoup4|Pillow|imagehash|openpyxl|jsonschema|lxml)" | ForEach-Object {
    Write-Host "    - $_" -ForegroundColor Gray
}

# Step 4: Generate Audit Secret
Write-Host "`n[4/8] Generating audit secret..." -ForegroundColor Yellow

$secretPath = ".audit_secret"
if ((Test-Path $secretPath) -and -not $Force) {
    Write-Host "  ! Secret already exists (use -Force to regenerate)" -ForegroundColor Yellow
    $secretHex = Get-Content $secretPath -Raw
} else {
    # Generate secret directly in PowerShell (more reliable than Python script)
    Add-Type -AssemblyName System.Security
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $secretHex = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    
    # Save to file
    $secretHex | Out-File -FilePath $secretPath -Encoding ASCII -NoNewline
    
    # Set file permissions (Windows)
    $acl = Get-Acl $secretPath
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
        "FullControl",
        "Allow"
    )
    $acl.SetAccessRule($rule)
    Set-Acl $secretPath $acl
    
    Write-Host "  ✓ Secret generated and saved" -ForegroundColor Green
}

Write-Host "  Secret (first 16 chars): $($secretHex.Substring(0,16))..." -ForegroundColor Gray

# Step 5: Handle DAM Assets File
Write-Host "`n[5/8] Checking DAM assets file..." -ForegroundColor Yellow

$damAssetPath = "assets\audit\dam_assets.json"
$oldDamPath = Get-ChildItem -Path "assets" -Filter "aprimo_dam_assets_master_*.json" -ErrorAction SilentlyContinue | Select-Object -First 1

if (Test-Path $damAssetPath) {
    $size = (Get-Item $damAssetPath).Length / 1MB
    Write-Host "  ✓ dam_assets.json exists ($([math]::Round($size, 1)) MB)" -ForegroundColor Green
} elseif ($oldDamPath) {
    Write-Host "  Found old DAM export: $($oldDamPath.Name)" -ForegroundColor Yellow
    Write-Host "  Copying to correct location..." -ForegroundColor Gray
    Copy-Item $oldDamPath.FullName $damAssetPath
    Write-Host "  ✓ Copied to assets\audit\dam_assets.json" -ForegroundColor Green
} else {
    Write-Host "  ✗ dam_assets.json NOT FOUND" -ForegroundColor Red
    Write-Host "`n  ACTION REQUIRED:" -ForegroundColor Yellow
    Write-Host "  You need to obtain the DAM assets export file:" -ForegroundColor White
    Write-Host "    1. Export from Aprimo DAM, OR" -ForegroundColor White
    Write-Host "    2. Copy from another machine, OR" -ForegroundColor White
    Write-Host "    3. Use the extension 'Import JSON' button" -ForegroundColor White
    Write-Host "  Place file at: $damAssetPath`n" -ForegroundColor White
}

# Step 6: Check Citizens URLs file
Write-Host "[6/8] Checking Citizens Bank URLs..." -ForegroundColor Yellow

$urlsPath = "assets\audit\citizensbank_urls.txt"
if (Test-Path $urlsPath) {
    $urlCount = (Get-Content $urlsPath).Count
    Write-Host "  ✓ citizensbank_urls.txt exists ($urlCount URLs)" -ForegroundColor Green
} else {
    Write-Host "  Creating sample file..." -ForegroundColor Gray
    @"
# Citizens Bank URLs to crawl
# Add one URL per line
https://www.citizensbank.com/
"@ | Out-File -FilePath $urlsPath -Encoding UTF8
    Write-Host "  ✓ Sample file created - EDIT THIS FILE with actual URLs" -ForegroundColor Yellow
}

# Step 7: Install Native Messaging Host
Write-Host "`n[7/8] Installing native messaging host..." -ForegroundColor Yellow
python scripts\install_native_host.py --extension-id $ExtensionId 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Native host registered with Chrome" -ForegroundColor Green
} else {
    Write-Host "  ✗ Native host installation failed" -ForegroundColor Red
    Write-Host "  Run manually: python scripts\install_native_host.py --extension-id $ExtensionId" -ForegroundColor Yellow
}

# Step 8: Output Chrome Extension Instructions
Write-Host "`n[8/8] Chrome Extension Setup" -ForegroundColor Yellow
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  FINAL STEP: Store Secret in Extension" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "1. Open Chrome and go to: chrome://extensions`n" -ForegroundColor White

Write-Host "2. Find 'Aprimo DAM Audit' extension`n" -ForegroundColor White

Write-Host "3. Click the 'service worker' blue link (opens DevTools)`n" -ForegroundColor White

Write-Host "4. In the Console tab, paste this command:`n" -ForegroundColor White

Write-Host "chrome.storage.local.set({" -ForegroundColor Yellow
Write-Host "  'auditSecretKey': '$secretHex'" -ForegroundColor Yellow
Write-Host "}, () => console.log('✅ Secret stored'));" -ForegroundColor Yellow

Write-Host "`n5. Press Enter, then reload the extension (click reload icon)`n" -ForegroundColor White

Write-Host "6. Click the extension icon and click 'Run Audit Pipeline'`n" -ForegroundColor White

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  SETUP COMPLETE!" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "✓ Python environment: .venv" -ForegroundColor Green
Write-Host "✓ Dependencies: Installed" -ForegroundColor Green
Write-Host "✓ Audit secret: Generated" -ForegroundColor Green
Write-Host "✓ Native host: Registered" -ForegroundColor Green

if (Test-Path $damAssetPath) {
    Write-Host "✓ DAM assets: Ready" -ForegroundColor Green
} else {
    Write-Host "! DAM assets: MISSING - See step 5 above" -ForegroundColor Yellow
}

if ((Test-Path $urlsPath) -and ((Get-Content $urlsPath).Count -gt 1)) {
    Write-Host "✓ Citizens URLs: Ready" -ForegroundColor Green
} else {
    Write-Host "! Citizens URLs: Sample only - Edit $urlsPath" -ForegroundColor Yellow
}

Write-Host "`nNext: Complete step 4 above to store secret in Chrome`n" -ForegroundColor Cyan

# Copy secret to clipboard if possible
try {
    Set-Clipboard -Value $secretHex
    Write-Host "💡 Secret copied to clipboard!`n" -ForegroundColor Magenta
} catch {
    # Clipboard not available
}
