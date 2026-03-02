#!/bin/bash
# Automated setup script for Aprimo DAM Audit Extension on Mac/Linux

set -e  # Exit on error

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Parse arguments
EXTENSION_ID=""
SKIP_SECRET=false
AUTO_FIX=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --extension-id)
            EXTENSION_ID="$2"
            shift 2
            ;;
        --skip-secret)
            SKIP_SECRET=true
            shift
            ;;
        --auto-fix)
            AUTO_FIX=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--extension-id ID] [--skip-secret] [--auto-fix]"
            exit 1
            ;;
    esac
done

# Helper functions
write_step() {
    echo -e "\n${CYAN}[$1/$2] $3${NC}"
}

write_success() {
    echo -e "  ${GREEN}✓ $1${NC}"
}

write_warning() {
    echo -e "  ${YELLOW}⚠ $1${NC}"
}

write_error() {
    echo -e "  ${RED}✗ $1${NC}"
}

write_info() {
    echo -e "  ${WHITE}ℹ $1${NC}"
}

# Header
clear
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  APRIMO DAM AUDIT EXTENSION - NEW MACHINE SETUP          ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"

# Check if running in extension directory
if [ ! -f "manifest.json" ]; then
    write_error "Must run from extension root directory"
    write_info "cd to aprimo_dam_crawler_extension folder first"
    exit 1
fi

TOTAL_STEPS=10

# Step 1: Check Python
write_step 1 $TOTAL_STEPS "Checking Python installation"

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    write_success "Python found: $PYTHON_VERSION"
    
    # Check version is 3.8+
    MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
    MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
    
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
        write_success "Version is 3.8+ ✓"
    else
        write_error "Python 3.8+ required (found $MAJOR.$MINOR)"
        write_info "Install from: https://www.python.org/downloads/"
        exit 1
    fi
else
    write_error "Python3 not found in PATH"
    write_info "Install Python 3.8+ from: https://www.python.org/downloads/"
    exit 1
fi

# Use python3 for all commands
PYTHON_CMD="python3"

# Step 2: Create virtual environment
write_step 2 $TOTAL_STEPS "Creating virtual environment"

if [ -d ".venv" ]; then
    write_warning "Virtual environment already exists"
    read -p "Recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf .venv
        $PYTHON_CMD -m venv .venv
        write_success "Virtual environment recreated"
    else
        write_info "Using existing virtual environment"
    fi
else
    $PYTHON_CMD -m venv .venv
    write_success "Virtual environment created (.venv/)"
fi

# Step 3: Activate virtual environment
write_step 3 $TOTAL_STEPS "Activating virtual environment"

source .venv/bin/activate
write_success "Virtual environment activated"

# Step 4: Install Python dependencies
write_step 4 $TOTAL_STEPS "Installing Python dependencies"

if [ -f "scripts/requirements-audit.txt" ]; then
    write_info "Installing from requirements-audit.txt..."
    pip install --upgrade pip --quiet
    pip install -r scripts/requirements-audit.txt --quiet
    write_success "Dependencies installed"
    
    # Verify key packages
    for pkg in requests beautifulsoup4 Pillow imagehash openpyxl jsonschema; do
        if $PYTHON_CMD -c "import ${pkg,,}" 2>/dev/null; then
            write_success "$pkg installed ✓"
        else
            write_warning "$pkg may not be installed correctly"
        fi
    done
else
    write_error "requirements-audit.txt not found in scripts/"
    exit 1
fi

# Step 5: Create required directories
write_step 5 $TOTAL_STEPS "Creating required directories"

for dir in "assets/audit" "reports"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        write_success "Created $dir/"
    else
        write_info "$dir/ already exists"
    fi
done

# Step 6: Check data files
write_step 6 $TOTAL_STEPS "Checking data files"

DAM_ASSETS_PATH="assets/audit/dam_assets.json"
URLS_PATH="assets/audit/citizensbank_urls.txt"

if [ -f "$DAM_ASSETS_PATH" ]; then
    SIZE=$(du -h "$DAM_ASSETS_PATH" | cut -f1)
    write_success "dam_assets.json found ($SIZE)"
else
    write_warning "dam_assets.json NOT FOUND"
    write_info "You need to:"
    write_info "  1. Export DAM assets from Aprimo, OR"
    write_info "  2. Copy dam_assets.json from another machine"
    write_info "  3. Place at: $DAM_ASSETS_PATH"
fi

if [ -f "$URLS_PATH" ]; then
    URL_COUNT=$(grep -v '^#' "$URLS_PATH" | grep -v '^$' | wc -l | tr -d ' ')
    write_success "citizensbank_urls.txt found ($URL_COUNT URLs)"
else
    if [ "$AUTO_FIX" = true ]; then
        write_warning "citizensbank_urls.txt NOT FOUND - creating sample"
        cat > "$URLS_PATH" << 'EOF'
# Citizens Bank URLs to crawl
# One URL per line (lines starting with # are ignored)

https://www.citizensbank.com/
https://www.citizensbank.com/personal-banking
https://www.citizensbank.com/business-banking
EOF
        write_success "Created sample citizensbank_urls.txt"
        write_info "Edit this file with your actual URLs"
    else
        write_warning "citizensbank_urls.txt NOT FOUND"
        write_info "Create at: $URLS_PATH"
        write_info "Run with --auto-fix to create sample file"
    fi
fi

# Step 7: Generate audit secret
write_step 7 $TOTAL_STEPS "Setting up audit secret"

SECRET_PATH=".audit_secret"

if [ -f "$SECRET_PATH" ]; then
    write_success ".audit_secret file already exists"
    write_info "Using existing secret (delete to regenerate)"
elif [ "$SKIP_SECRET" = true ]; then
    write_warning "Secret generation skipped (--skip-secret flag)"
    write_info "Copy .audit_secret from another machine"
else
    if [ -f "scripts/generate_audit_secret.py" ]; then
        write_info "Generating new audit secret..."
        SECRET_OUTPUT=$($PYTHON_CMD scripts/generate_audit_secret.py 2>&1)
        
        if [ -f "$SECRET_PATH" ]; then
            write_success "Audit secret generated"
            
            # Extract hex from output
            SECRET_HEX=$(echo "$SECRET_OUTPUT" | grep -oE '[0-9a-f]{64}' | head -n1)
            if [ -n "$SECRET_HEX" ]; then
                write_info "Secret (first 16 chars): ${SECRET_HEX:0:16}..."
                write_warning "IMPORTANT: Store this secret in Chrome extension storage!"
                echo
                write_info "In Chrome DevTools (Service Worker console), run:"
                echo -e "${YELLOW}  const { encryptedStorage } = await import(chrome.runtime.getURL('encrypted_storage.js'));${NC}"
                echo -e "${YELLOW}  await encryptedStorage.set({ auditSecretKey: '$SECRET_HEX' });${NC}"
                echo
            fi
        else
            write_warning "Secret generation script ran but file not created"
        fi
    else
        write_warning "generate_audit_secret.py not found"
    fi
fi

# Step 8: Install native messaging host
write_step 8 $TOTAL_STEPS "Configuring native messaging host"

if [ -z "$EXTENSION_ID" ]; then
    write_warning "Extension ID not provided"
    write_info "Steps to get Extension ID:"
    write_info "  1. Open chrome://extensions"
    write_info "  2. Enable 'Developer mode' (top-right)"
    write_info "  3. Click 'Load unpacked', select this folder"
    write_info "  4. Copy the Extension ID shown"
    write_info "  5. Re-run: ./setup_new_machine.sh --extension-id 'YOUR_ID_HERE'"
    echo
    write_info "Skipping native host installation..."
else
    write_info "Extension ID: $EXTENSION_ID"
    
    if [ -f "scripts/install_native_host.py" ]; then
        write_info "Installing native messaging host..."
        $PYTHON_CMD scripts/install_native_host.py --extension-id "$EXTENSION_ID"
        
        if [ $? -eq 0 ]; then
            write_success "Native messaging host configured"
        else
            write_warning "Native host installation may have failed"
        fi
    else
        write_warning "install_native_host.py not found"
    fi
fi

# Step 9: Run preflight check
write_step 9 $TOTAL_STEPS "Running preflight validation"

if [ -f "scripts/preflight_check.py" ]; then
    if [ "$AUTO_FIX" = true ]; then
        write_info "Running preflight check with auto-fix..."
        $PYTHON_CMD scripts/preflight_check.py --fix
    else
        write_info "Running preflight check..."
        $PYTHON_CMD scripts/preflight_check.py
    fi
    
    if [ $? -eq 0 ]; then
        write_success "All preflight checks passed! ✓"
    else
        write_warning "Some preflight checks failed"
        write_info "Run: python3 scripts/preflight_check.py --fix"
    fi
else
    write_warning "preflight_check.py not found (skipping)"
fi

# Step 10: Run enhancement tests
write_step 10 $TOTAL_STEPS "Testing enhancements"

if [ -f "scripts/test_enhancements.py" ]; then
    write_info "Running enhancement validation tests..."
    $PYTHON_CMD scripts/test_enhancements.py
    
    if [ $? -eq 0 ]; then
        write_success "All enhancement tests passed! ✓"
    fi
else
    write_info "test_enhancements.py not found (skipping)"
fi

# Summary
echo
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                    SETUP SUMMARY                          ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${WHITE}Setup Status:${NC}"
echo -e "  ${GREEN}✓ Python environment configured${NC}"
echo -e "  ${GREEN}✓ Dependencies installed${NC}"
echo -e "  ${GREEN}✓ Directories created${NC}"

if [ -f "$DAM_ASSETS_PATH" ]; then
    echo -e "  ${GREEN}✓ DAM assets file ready${NC}"
else
    echo -e "  ${YELLOW}⚠ DAM assets file MISSING${NC}"
fi

if [ -f "$URLS_PATH" ]; then
    echo -e "  ${GREEN}✓ URL list ready${NC}"
else
    echo -e "  ${YELLOW}⚠ URL list MISSING${NC}"
fi

if [ -f "$SECRET_PATH" ]; then
    echo -e "  ${GREEN}✓ Audit secret generated${NC}"
else
    echo -e "  ${YELLOW}⚠ Audit secret MISSING${NC}"
fi

if [ -n "$EXTENSION_ID" ]; then
    echo -e "  ${GREEN}✓ Native messaging configured${NC}"
else
    echo -e "  ${YELLOW}⚠ Native messaging NOT configured${NC}"
fi

echo -e "\n${CYAN}Next Steps:${NC}"

STEP_NUM=1
if [ -z "$EXTENSION_ID" ]; then
    echo -e "  ${WHITE}$STEP_NUM. Load extension in Chrome:${NC}"
    echo -e "     ${GRAY}- Open chrome://extensions${NC}"
    echo -e "     ${GRAY}- Enable 'Developer mode'${NC}"
    echo -e "     ${GRAY}- Click 'Load unpacked'${NC}"
    echo -e "     ${GRAY}- Select this folder${NC}"
    echo -e "     ${GRAY}- Copy Extension ID${NC}"
    echo -e "     ${GRAY}- Re-run: ./setup_new_machine.sh --extension-id 'ID_HERE'${NC}"
    ((STEP_NUM++))
fi

if [ ! -f "$SECRET_PATH" ] || [ -n "$EXTENSION_ID" ]; then
    echo -e "  ${WHITE}$STEP_NUM. Store secret in extension:${NC}"
    echo -e "     ${GRAY}- Open Chrome DevTools → Service Worker${NC}"
    echo -e "     ${GRAY}- Run the commands shown above${NC}"
    ((STEP_NUM++))
fi

if [ ! -f "$DAM_ASSETS_PATH" ]; then
    echo -e "  ${WHITE}$STEP_NUM. Add DAM assets:${NC}"
    echo -e "     ${GRAY}- Export from Aprimo or copy from another machine${NC}"
    echo -e "     ${GRAY}- Place at: assets/audit/dam_assets.json${NC}"
    ((STEP_NUM++))
fi

if [ ! -f "$URLS_PATH" ]; then
    echo -e "  ${WHITE}$STEP_NUM. Add Citizens Bank URLs:${NC}"
    echo -e "     ${GRAY}- Edit: assets/audit/citizensbank_urls.txt${NC}"
    echo -e "     ${GRAY}- Add URLs (one per line)${NC}"
    ((STEP_NUM++))
fi

echo -e "  ${WHITE}$STEP_NUM. Test the extension:${NC}"
echo -e "     ${GRAY}- Click extension icon in Chrome${NC}"
echo -e "     ${GRAY}- Click 'Run Audit Pipeline'${NC}"
echo -e "     ${GRAY}- Monitor progress${NC}"

echo -e "\n${CYAN}Alternative (CLI mode):${NC}"
echo -e "  ${YELLOW}python3 scripts/run_audit_standalone.py${NC}"

echo -e "\n${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              SETUP COMPLETE - READY TO RUN!               ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo
