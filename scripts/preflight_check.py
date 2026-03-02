#!/usr/bin/env python3
"""
Pre-flight checklist for Aprimo DAM Audit Pipeline
Validates all requirements before running the audit
"""

import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# Track issues and warnings
issues = []
warnings = []
checks_passed = 0
checks_total = 10

# Global flags
auto_fix = False
verbose_mode = False

# Paths
script_dir = Path(__file__).parent
project_dir = script_dir.parent
audit_dir = project_dir / "assets" / "audit"
dam_json = audit_dir / "dam_assets.json"
urls_file = audit_dir / "citizensbank_urls.txt"


def print_header():
    """Print the preflight check header"""
    print("\n╔═══════════════════════════════════════════════════════════╗")
    print("║     APRIMO DAM AUDIT PIPELINE - PRE-FLIGHT CHECK         ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")


def check_python_version():
    """Check Python version is 3.8+"""
    global checks_passed
    print("[1/10] Checking Python version...")
    
    version = sys.version_info
    if version >= (3, 8):
        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro} (required: 3.8+)")
        checks_passed += 1
        return True
    else:
        issues.append(
            f"Python {version.major}.{version.minor} is too old (need 3.8+)\n"
            f"  SOLUTION: Install Python 3.8 or higher from python.org"
        )
        print(f"  ✗ Python {version.major}.{version.minor}.{version.micro} (required: 3.8+)")
        return False


def check_packages():
    """Check required Python packages are installed"""
    global checks_passed
    print("[2/10] Checking required packages...")
    
    required = {
        'requests': 'requests',
        'bs4': 'beautifulsoup4',
        'PIL': 'Pillow',
        'imagehash': 'imagehash',
        'openpyxl': 'openpyxl'
    }
    
    missing = []
    for import_name, package_name in required.items():
        try:
            mod = __import__(import_name)
            version = getattr(mod, '__version__', 'unknown')
            print(f"  ✓ {package_name} ({version})")
        except ImportError:
            missing.append(package_name)
            print(f"  ✗ {package_name} not installed")
    
    if missing:
        issues.append(
            f"Missing packages: {', '.join(missing)}\n"
            f"  SOLUTION: pip install {' '.join(missing)}\n"
            f"  OR: pip install -r scripts/requirements-audit.txt"
        )
        return False
    
    checks_passed += 1
    return True


def check_directory_structure():
    """Check required directories exist"""
    global checks_passed
    print("[3/10] Checking directory structure...")
    
    required_dirs = [
        script_dir,
        project_dir / "assets",
        audit_dir
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if dir_path.exists():
            print(f"  ✓ {dir_path.relative_to(project_dir)}/ exists")
        else:
            if auto_fix:
                print(f"  🔧 AUTO-FIX: Creating {dir_path.relative_to(project_dir)}/...", end=" ")
                dir_path.mkdir(parents=True, exist_ok=True)
                print("DONE")
                warnings.append(f"Created missing directory: {dir_path.relative_to(project_dir)}")
            else:
                issues.append(f"Missing directory: {dir_path}")
                print(f"  ✗ {dir_path.relative_to(project_dir)}/ not found")
                all_exist = False
    
    if all_exist or auto_fix:
        checks_passed += 1
        return True
    return False


def check_dam_json():
    """Check for DAM assets JSON file"""
    global checks_passed
    print("[4/10] Checking DAM assets JSON...")
    
    # Check if standard name exists
    if dam_json.exists():
        size_mb = dam_json.stat().st_size / (1024 * 1024)
        print(f"  ✓ Found: dam_assets.json ({size_mb:.1f} MB)")
        
        # Validate JSON format
        try:
            with open(dam_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                issues.append("dam_assets.json must be a JSON array")
                print(f"  ✗ Invalid format (expected array, got {type(data).__name__})")
                return False
            
            asset_count = len(data)
            print(f"  ✓ Valid JSON format")
            print(f"  ✓ Contains {asset_count:,} assets")
            
            # Validate first asset has expected fields
            if asset_count > 0:
                first_asset = data[0]
                has_id = any(k in first_asset for k in ['id', 'item_id', 'asset_id'])
                if has_id:
                    print(f"  ✓ Asset schema valid")
                else:
                    warnings.append("Assets may be missing ID fields")
                    print(f"  ⚠ First asset missing ID field")
            
            checks_passed += 1
            return True
            
        except json.JSONDecodeError as e:
            issues.append(f"dam_assets.json is not valid JSON: {e}")
            print(f"  ✗ Invalid JSON format (syntax error at line {e.lineno})")
            return False
    
    # Look for aprimo_dam_assets_master_*.json files
    master_files = list(audit_dir.glob("aprimo_dam_assets_master_*.json"))
    
    if master_files:
        master_file = master_files[0]
        size_mb = master_file.stat().st_size / (1024 * 1024)
        print(f"  ⚠ dam_assets.json not found")
        print(f"  ✓ Found: {master_file.name} ({size_mb:.1f} MB)")
        
        if auto_fix:
            print(f"  🔧 AUTO-FIX: Renaming to dam_assets.json...", end=" ")
            master_file.rename(dam_json)
            print("DONE")
            warnings.append("Renamed DAM assets file to standard name")
            checks_passed += 1
            return True
        else:
            issues.append(
                f"DAM file found as '{master_file.name}' but should be 'dam_assets.json'\n"
                f"  SOLUTION: Rename the file:\n"
                f"    cd assets\\audit\n"
                f"    ren \"{master_file.name}\" dam_assets.json\n"
                f"  OR run with --fix flag: python scripts\\preflight_check.py --fix"
            )
            print(f"  ✗ File needs to be renamed to dam_assets.json")
            return False
    
    # No DAM file found at all
    issues.append(
        "No DAM assets JSON file found\n"
        "  SOLUTION:\n"
        "    1. Export DAM assets from Aprimo\n"
        "    2. Save to: assets/audit/dam_assets.json\n"
        "    OR run the DAM crawler to generate it"
    )
    print(f"  ✗ dam_assets.json not found")
    print(f"  ✗ No aprimo_dam_assets_master_*.json found either")
    return False


def check_urls_file():
    """Check for Citizens Bank URLs list"""
    global checks_passed
    print("[5/10] Checking Citizens Bank URL list...")
    
    if urls_file.exists():
        content = urls_file.read_text(encoding='utf-8').strip()
        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
        
        if not lines:
            if auto_fix:
                print(f"  ⚠ File exists but is empty")
                print(f"  🔧 AUTO-FIX: Creating sample URL list...", end=" ")
                sample_urls = """# Citizens Bank URLs to crawl
# One URL per line (lines starting with # are ignored)

https://www.citizensbank.com/
https://www.citizensbank.com/personal-banking
https://www.citizensbank.com/business-banking
"""
                urls_file.write_text(sample_urls, encoding='utf-8')
                print("DONE")
                warnings.append("Created sample URL list - please edit with real URLs")
                print(f"  📝 Please edit assets/audit/citizensbank_urls.txt with your target URLs")
                checks_passed += 1
                return True
            else:
                issues.append(
                    "citizensbank_urls.txt is empty\n"
                    "  SOLUTION: Add target URLs (one per line)"
                )
                print(f"  ✗ File is empty (no URLs to crawl)")
                return False
        
        print(f"  ✓ Found: citizensbank_urls.txt")
        print(f"  ✓ Contains {len(lines):,} URLs")
        
        # Validate first few URLs
        invalid_urls = []
        for url in lines[:5]:
            if not url.startswith('http'):
                invalid_urls.append(url)
        
        if invalid_urls:
            warnings.append(f"Some URLs may be invalid: {invalid_urls[:2]}")
            print(f"  ⚠ Some URLs may be invalid (check format)")
        
        checks_passed += 1
        return True
    
    # File doesn't exist
    if auto_fix:
        print(f"  ⚠ citizensbank_urls.txt not found")
        print(f"  🔧 AUTO-FIX: Creating sample URL list...", end=" ")
        sample_urls = """# Citizens Bank URLs to crawl
# One URL per line (lines starting with # are ignored)

https://www.citizensbank.com/
https://www.citizensbank.com/personal-banking
https://www.citizensbank.com/business-banking
"""
        urls_file.write_text(sample_urls, encoding='utf-8')
        print("DONE")
        warnings.append("Created sample URL list - please edit with real URLs")
        print(f"  📝 Please edit assets/audit/citizensbank_urls.txt with your target URLs")
        checks_passed += 1
        return True
    
    issues.append(
        "citizensbank_urls.txt not found\n"
        "  SOLUTION: Create file with URLs to crawl (one per line)"
    )
    print(f"  ✗ citizensbank_urls.txt not found")
    return False


def check_audit_scripts():
    """Check all audit stage scripts exist and are valid"""
    global checks_passed
    print("[6/10] Checking audit scripts...")
    
    required_scripts = [
        "01_crawl_citizens_images.py",
        "02_build_dam_fingerprints.py",
        "03_build_citizens_fingerprints.py",
        "04_match_assets.py",
        "05_build_reports.py"
    ]
    
    all_found = True
    for script in required_scripts:
        script_path = script_dir / script
        if script_path.exists():
            # Verify it's a valid Python file
            try:
                with open(script_path, 'r', encoding='utf-8') as f:
                    content = f.read(200)
                    # Check for Python indicators
                    if 'import' in content or 'def ' in content or 'class ' in content:
                        print(f"  ✓ {script}")
                    else:
                        warnings.append(f"{script} may not be a valid Python file")
                        print(f"  ⚠ {script} (file format warning)")
            except Exception as e:
                issues.append(f"Cannot read {script}: {e}")
                print(f"  ✗ {script} (read error)")
                all_found = False
        else:
            issues.append(f"Missing required script: {script}")
            print(f"  ✗ {script} (not found)")
            all_found = False
    
    if all_found:
        checks_passed += 1
        return True
    return False


def check_domain_whitelist():
    """Check domain whitelist configuration"""
    global checks_passed
    print("[7/10] Checking domain whitelist...")
    
    # Check audit_common.py for ALLOWED_DOMAINS
    audit_common = script_dir / "audit_common.py"
    
    if not audit_common.exists():
        warnings.append("audit_common.py not found (cannot verify whitelist)")
        print(f"  ⚠ audit_common.py not found (skipped)")
        checks_passed += 1
        return True
    
    try:
        with open(audit_common, 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_domains = ['citizensbank.com', 'aprimo.com']
        found_domains = []
        
        for domain in required_domains:
            if domain in content:
                found_domains.append(domain)
                print(f"  ✓ {domain} (and subdomains)")
            else:
                print(f"  ⚠ {domain} not found in whitelist")
        
        if len(found_domains) >= 2:
            checks_passed += 1
            return True
        else:
            warnings.append("Domain whitelist may be incomplete")
            return True  # Don't fail, just warn
        
    except Exception as e:
        warnings.append(f"Cannot read audit_common.py: {e}")
        print(f"  ⚠ Cannot verify whitelist (skipped)")
        checks_passed += 1
        return True


def check_disk_space():
    """Check available disk space"""
    global checks_passed
    print("[8/10] Checking disk space...")
    
    try:
        stat = shutil.disk_usage(audit_dir)
        available_gb = stat.free / (1024 ** 3)
        required_gb = 5
        
        if available_gb >= required_gb:
            print(f"  ✓ Available: {available_gb:.1f} GB (required: {required_gb} GB)")
            checks_passed += 1
            return True
        else:
            issues.append(
                f"Insufficient disk space: {available_gb:.1f} GB available, need {required_gb} GB\n"
                f"  SOLUTION: Free up at least {required_gb - available_gb:.1f} GB"
            )
            print(f"  ✗ Available: {available_gb:.1f} GB (required: {required_gb} GB)")
            return False
    except Exception as e:
        warnings.append(f"Cannot check disk space: {e}")
        print(f"  ⚠ Cannot check disk space (skipped)")
        checks_passed += 1
        return True


def check_network():
    """Check network connectivity to required domains"""
    global checks_passed
    print("[9/10] Checking network connectivity...")
    
    try:
        import requests
    except ImportError:
        warnings.append("requests package not installed (cannot test network)")
        print(f"  ⚠ Cannot test (requests not installed)")
        checks_passed += 1
        return True
    
    test_urls = [
        "https://www.citizensbank.com",
        "https://aprimo.com"
    ]
    
    all_reachable = True
    for url in test_urls:
        try:
            response = requests.head(
                url,
                timeout=10,
                allow_redirects=True,
                headers={'User-Agent': 'Aprimo-DAM-Audit/1.0'}
            )
            domain = url.split("//")[1]
            print(f"  ✓ Can reach {domain}")
        except requests.Timeout:
            warnings.append(f"Network timeout connecting to {url}")
            print(f"  ⚠ {url.split('//')[1]} (timeout - may be slow)")
        except requests.RequestException as e:
            warnings.append(f"Cannot reach {url}: {str(e)[:50]}")
            print(f"  ⚠ {url.split('//')[1]} (connection failed)")
            # Don't fail on network issues - might be VPN/firewall
    
    checks_passed += 1
    return True


def check_chrome_extension():
    """Check if Chrome extension is accessible (optional)"""
    global checks_passed
    print("[10/10] Checking Chrome extension...")
    
    # This is optional - audit can run via CLI
    # Just check if native host manifest exists
    
    if sys.platform == 'win32':
        manifest_path = Path.home() / "AppData/Local/aprimo_dam_audit/native_host_manifest.json"
    elif sys.platform == 'darwin':
        manifest_path = Path.home() / "Library/Application Support/aprimo_dam_audit/native_host_manifest.json"
    else:
        manifest_path = Path.home() / ".config/aprimo_dam_audit/native_host_manifest.json"
    
    if manifest_path.exists():
        print(f"  ✓ Native host manifest found")
        print(f"     Extension can communicate with Python")
        checks_passed += 1
        return True
    else:
        warnings.append(
            "Chrome extension not configured (optional)\n"
            "  Can still run via CLI: python scripts/run_audit_standalone.py"
        )
        print(f"  ⚠ Native host not configured (use CLI mode)")
        checks_passed += 1
        return True


def print_summary():
    """Print final summary"""
    print("\n╔═══════════════════════════════════════════════════════════╗")
    print("║                    PREFLIGHT SUMMARY                      ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")
    
    # Overall status
    if not issues:
        print("Status: ✅ READY TO RUN\n")
    elif len(issues) <= 2:
        print("Status: ⚠️  MINOR ISSUES (may still run)\n")
    else:
        print("Status: ❌ CRITICAL ISSUES (fix before running)\n")
    
    # Checks summary
    print(f"✓ {checks_passed}/{checks_total} checks passed")
    if warnings:
        print(f"⚠ {len(warnings)} warning(s)")
    if issues:
        print(f"✗ {len(issues)} issue(s)\n")
    else:
        print()
    
    # List issues
    if issues:
        print("Issues to fix:")
        for i, issue in enumerate(issues, 1):
            print(f"\n{i}. {issue}")
        print()
    
    # List warnings
    if warnings and verbose_mode:
        print("Warnings:")
        for i, warning in enumerate(warnings, 1):
            print(f"\n{i}. {warning}")
        print()
    
    # System information
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                  SYSTEM INFORMATION                       ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")
    
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    print(f"Working Directory: {project_dir.name}/")
    
    if dam_json.exists():
        size_mb = dam_json.stat().st_size / (1024 * 1024)
        try:
            with open(dam_json, 'r', encoding='utf-8') as f:
                asset_count = len(json.load(f))
            print(f"DAM Dataset: {asset_count:,} assets ({size_mb:.1f} MB)")
        except:
            print(f"DAM Dataset: {size_mb:.1f} MB")
    
    if urls_file.exists():
        try:
            lines = [l.strip() for l in urls_file.read_text().split('\n') if l.strip() and not l.startswith('#')]
            print(f"Target URLs: {len(lines):,}")
        except:
            pass
    
    # Estimates
    if not issues:
        print("\nEstimated Runtime: 7-17 minutes")
        print("Expected Output Size: ~2.5 GB")
    
    # Next steps
    if not issues:
        print("\n╔═══════════════════════════════════════════════════════════╗")
        print("║                    NEXT STEPS                             ║")
        print("╚═══════════════════════════════════════════════════════════╝\n")
        
        print("Option 1: Run via Chrome Extension")
        print("  1. Open Chrome browser")
        print("  2. Click extension icon")
        print("  3. Click \"Run Audit Pipeline\"\n")
        
        print("Option 2: Run via CLI")
        print("  python scripts\\run_audit_standalone.py\n")
        
        print("Option 3: Monitor with PowerShell")
        print("  .\\scripts\\watch_audit.ps1")


def save_report():
    """Save preflight report to file"""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    report_path = audit_dir / f"preflight_report_{timestamp}.txt"
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"Aprimo DAM Audit - Preflight Report\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"=" * 60 + "\n\n")
            
            f.write(f"Checks Passed: {checks_passed}/{checks_total}\n")
            f.write(f"Issues: {len(issues)}\n")
            f.write(f"Warnings: {len(warnings)}\n\n")
            
            if issues:
                f.write("ISSUES:\n")
                for i, issue in enumerate(issues, 1):
                    f.write(f"{i}. {issue}\n\n")
            
            if warnings:
                f.write("WARNINGS:\n")
                for i, warning in enumerate(warnings, 1):
                    f.write(f"{i}. {warning}\n\n")
            
            f.write(f"\nPython: {sys.version}\n")
            f.write(f"Platform: {sys.platform}\n")
        
        if verbose_mode:
            print(f"\n📄 Report saved: {report_path.relative_to(project_dir)}")
    except Exception as e:
        if verbose_mode:
            print(f"\n⚠ Could not save report: {e}")


def main():
    """Main preflight check routine"""
    global auto_fix, verbose_mode
    
    parser = argparse.ArgumentParser(description="Pre-flight check for DAM audit pipeline")
    parser.add_argument('--fix', action='store_true', help='Automatically fix issues')
    parser.add_argument('--verbose', action='store_true', help='Show detailed diagnostics')
    parser.add_argument('--quiet', action='store_true', help='Only show summary')
    args = parser.parse_args()
    
    auto_fix = args.fix
    verbose_mode = args.verbose
    
    if not args.quiet:
        print_header()
    
    # Run all checks
    check_python_version()
    check_packages()
    check_directory_structure()
    check_dam_json()
    check_urls_file()
    check_audit_scripts()
    check_domain_whitelist()
    check_disk_space()
    check_network()
    check_chrome_extension()
    
    if not args.quiet:
        print_summary()
        save_report()
    
    # Exit code
    if issues:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
