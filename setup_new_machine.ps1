#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Automated setup script for Aprimo DAM Audit Extension on a new machine

.DESCRIPTION
    Sets up Python environment, installs dependencies, configures native messaging,
    and validates the installation is ready to run.

.PARAMETER ExtensionId
    Chrome extension ID (copy from chrome://extensions after loading the extension)

.PARAMETER SkipSecret
    Skip secret generation (useful if copying from another machine)

.PARAMETER AutoFix
    Automatically fix issues found during preflight check

.EXAMPLE
    .\setup_new_machine.ps1 -ExtensionId "mgpfabhbihecophkkeiphcmjkeilafpf"

.EXAMPLE
    .\setup_new_machine.ps1 -ExtensionId "mgpfabhbihecophkkeiphcmjkeilafpf" -SkipSecret -AutoFix
#>

param(
    [string]$ExtensionId = "",
    [switch]$SkipSecret = $false,
    [switch]$AutoFix = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Color output functions
function Write-Step {
    param([string]$Message, [int]$Step, [int]$Total)
    Write-Host "`n[$Step/$Total] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  ✓ $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  ⚠ $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "  ✗ $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "  ℹ $Message" -ForegroundColor White
}

# Header
Clear-Host
Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  APRIMO DAM AUDIT EXTENSION - NEW MACHINE SETUP          ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

# Check if running in extension directory
if (-not (Test-Path ".\manifest.json")) {
    Write-Error "Must run from extension root directory"
    Write-Info "cd to aprimo_dam_crawler_extension folder first"
    exit 1
}

# Total steps
$TotalSteps = 10

# Step 1: Check Python
Write-Step "Checking Python installation" 1 $TotalSteps

try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Python found: $pythonVersion"
        
        # Check version is 3.8+
        if ($pythonVersion -match "Python (\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            if ($major -ge 3 -and $minor -ge 8) {
                Write-Success "Version is 3.8+ ✓"
            } else {
                Write-Error "Python 3.8+ required (found $major.$minor)"
                Write-Info "Download from: https://www.python.org/downloads/"
                exit 1
            }
        }
    }
} catch {
    Write-Error "Python not found in PATH"
    Write-Info "Install Python 3.8+ from: https://www.python.org/downloads/"
    Write-Info "Make sure to check 'Add Python to PATH' during installation"
    exit 1
}

# Step 2: Create virtual environment
Write-Step "Creating virtual environment" 2 $TotalSteps

if (Test-Path ".\.venv") {
    Write-Warning "Virtual environment already exists"
    $recreate = Read-Host "Recreate it? (y/N)"
    if ($recreate -eq "y") {
        Remove-Item -Recurse -Force .\.venv
        python -m venv .venv
        Write-Success "Virtual environment recreated"
    } else {
        Write-Info "Using existing virtual environment"
    }
} else {
    python -m venv .venv
    Write-Success "Virtual environment created (.venv/)"
}

# Step 3: Activate virtual environment
Write-Step "Activating virtual environment" 3 $TotalSteps

# Check execution policy
$executionPolicy = Get-ExecutionPolicy -Scope CurrentUser
if ($executionPolicy -eq "Restricted") {
    Write-Warning "PowerShell execution policy is Restricted"
    Write-Info "Changing to RemoteSigned for current user..."
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
    Write-Success "Execution policy updated"
}

# Activate
try {
    & .\.venv\Scripts\Activate.ps1
    Write-Success "Virtual environment activated"
} catch {
    Write-Error "Failed to activate virtual environment: $_"
    exit 1
}

# Step 4: Install Python dependencies
Write-Step "Installing Python dependencies" 4 $TotalSteps

if (Test-Path ".\scripts\requirements-audit.txt") {
    Write-Info "Installing from requirements-audit.txt..."
    pip install --upgrade pip --quiet
    pip install -r .\scripts\requirements-audit.txt --quiet
    Write-Success "Dependencies installed"
    
    # Verify key packages
    $packages = @("requests", "beautifulsoup4", "Pillow", "imagehash", "openpyxl", "jsonschema")
    foreach ($pkg in $packages) {
        try {
            python -c "import $($pkg.ToLower()); print('OK')" 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Success "$pkg installed ✓"
            }
        } catch {
            Write-Warning "$pkg may not be installed correctly"
        }
    }
} else {
    Write-Error "requirements-audit.txt not found in scripts/"
    exit 1
}

# Step 5: Create required directories
Write-Step "Creating required directories" 5 $TotalSteps

$dirs = @(
    "assets\audit",
    "reports"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Success "Created $dir/"
    } else {
        Write-Info "$dir/ already exists"
    }
}

# Step 6: Check data files
Write-Step "Checking data files" 6 $TotalSteps

$damAssetsPath = "assets\audit\dam_assets.json"
$urlsPath = "assets\audit\citizensbank_urls.txt"

if (Test-Path $damAssetsPath) {
    $size = (Get-Item $damAssetsPath).Length / 1MB
    Write-Success "dam_assets.json found ($([math]::Round($size, 1)) MB)"
} else {
    Write-Warning "dam_assets.json NOT FOUND"
    Write-Info "You need to:"
    Write-Info "  1. Export DAM assets from Aprimo, OR"
    Write-Info "  2. Copy dam_assets.json from another machine"
    Write-Info "  3. Place at: $damAssetsPath"
}

if (Test-Path $urlsPath) {
    $urlCount = (Get-Content $urlsPath | Where-Object { $_ -and -not $_.StartsWith("#") }).Count
    Write-Success "citizensbank_urls.txt found ($urlCount URLs)"
} else {
    if ($AutoFix) {
        Write-Warning "citizensbank_urls.txt NOT FOUND - creating sample"
        $sampleUrls = @"
# Citizens Bank URLs to crawl
# One URL per line (lines starting with # are ignored)

https://www.citizensbank.com/
https://www.citizensbank.com/personal-banking
https://www.citizensbank.com/business-banking
"@
        $sampleUrls | Out-File -FilePath $urlsPath -Encoding UTF8
        Write-Success "Created sample citizensbank_urls.txt"
        Write-Info "Edit this file with your actual URLs"
    } else {
        Write-Warning "citizensbank_urls.txt NOT FOUND"
        Write-Info "Create at: $urlsPath"
        Write-Info "Run with -AutoFix to create sample file"
    }
}

# Step 7: Generate audit secret
Write-Step "Setting up audit secret" 7 $TotalSteps

$secretPath = ".\.audit_secret"

if (Test-Path $secretPath) {
    Write-Success ".audit_secret file already exists"
    Write-Info "Using existing secret (delete to regenerate)"
} elseif ($SkipSecret) {
    Write-Warning "Secret generation skipped (-SkipSecret flag)"
    Write-Info "Copy .audit_secret from another machine"
} else {
    if (Test-Path ".\scripts\generate_audit_secret.py") {
        Write-Info "Generating new audit secret..."
        $secretOutput = python .\scripts\generate_audit_secret.py 2>&1
        
        if (Test-Path $secretPath) {
            Write-Success "Audit secret generated"
            
            # Extract hex from output
            $hexMatch = $secretOutput | Select-String -Pattern "([0-9a-f]{64})"
            if ($hexMatch) {
                $secretHex = $hexMatch.Matches[0].Value
                Write-Info "Secret (first 16 chars): $($secretHex.Substring(0, 16))..."
                Write-Warning "IMPORTANT: Store this secret in Chrome extension storage!"
                Write-Info ""
                Write-Info "In Chrome DevTools (Service Worker console), run:"
                Write-Host "  const { encryptedStorage } = await import(chrome.runtime.getURL('encrypted_storage.js'));" -ForegroundColor Yellow
                Write-Host "  await encryptedStorage.set({ auditSecretKey: '$secretHex' });" -ForegroundColor Yellow
                Write-Info ""
            }
        } else {
            Write-Warning "Secret generation script ran but file not created"
        }
    } else {
        Write-Warning "generate_audit_secret.py not found"
    }
}

# Step 8: Install native messaging host
Write-Step "Configuring native messaging host" 8 $TotalSteps

if ($ExtensionId -eq "") {
    Write-Warning "Extension ID not provided"
    Write-Info "Steps to get Extension ID:"
    Write-Info "  1. Open chrome://extensions"
    Write-Info "  2. Enable 'Developer mode' (top-right)"
    Write-Info "  3. Click 'Load unpacked', select this folder"
    Write-Info "  4. Copy the Extension ID shown"
    Write-Info "  5. Re-run: .\setup_new_machine.ps1 -ExtensionId 'YOUR_ID_HERE'"
    Write-Info ""
    Write-Info "Skipping native host installation..."
} else {
    Write-Info "Extension ID: $ExtensionId"
    
    if (Test-Path ".\scripts\install_native_host.py") {
        Write-Info "Installing native messaging host..."
        python .\scripts\install_native_host.py --extension-id $ExtensionId
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Native messaging host configured"
            
            # Verify registry entry (Windows)
            if ($IsWindows -or $env:OS -match "Windows") {
                $regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.aprimo.dam_audit"
                if (Test-Path $regPath) {
                    Write-Success "Registry entry created ✓"
                } else {
                    Write-Warning "Registry entry not found (may need manual setup)"
                }
            }
        } else {
            Write-Warning "Native host installation may have failed"
        }
    } else {
        Write-Warning "install_native_host.py not found"
    }
}

# Step 9: Run preflight check
Write-Step "Running preflight validation" 9 $TotalSteps

if (Test-Path ".\scripts\preflight_check.py") {
    if ($AutoFix) {
        Write-Info "Running preflight check with auto-fix..."
        python .\scripts\preflight_check.py --fix
    } else {
        Write-Info "Running preflight check..."
        python .\scripts\preflight_check.py
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "All preflight checks passed! ✓"
    } else {
        Write-Warning "Some preflight checks failed"
        Write-Info "Run: python scripts\preflight_check.py --fix"
    }
} else {
    Write-Warning "preflight_check.py not found (skipping)"
}

# Step 10: Run enhancement tests
Write-Step "Testing enhancements" 10 $TotalSteps

if (Test-Path ".\scripts\test_enhancements.py") {
    Write-Info "Running enhancement validation tests..."
    python .\scripts\test_enhancements.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "All enhancement tests passed! ✓"
    }
} else {
    Write-Info "test_enhancements.py not found (skipping)"
}

# Summary
Write-Host "`n╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                    SETUP SUMMARY                          ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

Write-Host "`nSetup Status:" -ForegroundColor White
Write-Host "  ✓ Python environment configured" -ForegroundColor Green
Write-Host "  ✓ Dependencies installed" -ForegroundColor Green
Write-Host "  ✓ Directories created" -ForegroundColor Green

if (Test-Path $damAssetsPath) {
    Write-Host "  ✓ DAM assets file ready" -ForegroundColor Green
} else {
    Write-Host "  ⚠ DAM assets file MISSING" -ForegroundColor Yellow
}

if (Test-Path $urlsPath) {
    Write-Host "  ✓ URL list ready" -ForegroundColor Green
} else {
    Write-Host "  ⚠ URL list MISSING" -ForegroundColor Yellow
}

if (Test-Path $secretPath) {
    Write-Host "  ✓ Audit secret generated" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Audit secret MISSING" -ForegroundColor Yellow
}

if ($ExtensionId -ne "") {
    Write-Host "  ✓ Native messaging configured" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Native messaging NOT configured" -ForegroundColor Yellow
}

Write-Host "`nNext Steps:" -ForegroundColor Cyan

$stepNum = 1
if ($ExtensionId -eq "") {
    Write-Host "  $stepNum. Load extension in Chrome:" -ForegroundColor White
    Write-Host "     - Open chrome://extensions" -ForegroundColor Gray
    Write-Host "     - Enable 'Developer mode'" -ForegroundColor Gray
    Write-Host "     - Click 'Load unpacked'" -ForegroundColor Gray
    Write-Host "     - Select this folder" -ForegroundColor Gray
    Write-Host "     - Copy Extension ID" -ForegroundColor Gray
    Write-Host "     - Re-run: .\setup_new_machine.ps1 -ExtensionId 'ID_HERE'" -ForegroundColor Gray
    $stepNum++
}

if (-not (Test-Path $secretPath) -or $ExtensionId -ne "") {
    Write-Host "  $stepNum. Store secret in extension:" -ForegroundColor White
    Write-Host "     - Open Chrome DevTools → Service Worker" -ForegroundColor Gray
    Write-Host "     - Run the commands shown above" -ForegroundColor Gray
    $stepNum++
}

if (-not (Test-Path $damAssetsPath)) {
    Write-Host "  $stepNum. Add DAM assets:" -ForegroundColor White
    Write-Host "     - Export from Aprimo or copy from another machine" -ForegroundColor Gray
    Write-Host "     - Place at: assets\audit\dam_assets.json" -ForegroundColor Gray
    $stepNum++
}

if (-not (Test-Path $urlsPath)) {
    Write-Host "  $stepNum. Add Citizens Bank URLs:" -ForegroundColor White
    Write-Host "     - Edit: assets\audit\citizensbank_urls.txt" -ForegroundColor Gray
    Write-Host "     - Add URLs (one per line)" -ForegroundColor Gray
    $stepNum++
}

Write-Host "  $stepNum. Test the extension:" -ForegroundColor White
Write-Host "     - Click extension icon in Chrome" -ForegroundColor Gray
Write-Host "     - Click 'Run Audit Pipeline'" -ForegroundColor Gray
Write-Host "     - Monitor progress" -ForegroundColor Gray

Write-Host "`nAlternative (CLI mode):" -ForegroundColor Cyan
Write-Host "  python scripts\run_audit_standalone.py" -ForegroundColor Yellow

Write-Host "`n╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              SETUP COMPLETE - READY TO RUN!               ║" -ForegroundColor Green
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host ""
