#!/usr/bin/env python3
"""
Install native messaging host for Aprimo DAM Audit Extension
Configures Chrome to communicate with Python scripts via native messaging
"""

import argparse
import json
import os
import sys
from pathlib import Path


def get_manifest_path():
    """Get the native messaging manifest path for this platform"""
    if sys.platform == 'win32':
        # Windows: Use AppData\Local
        base = Path(os.environ.get('LOCALAPPDATA', ''))
        return base / 'aprimo_dam_audit' / 'native_host_manifest.json'
    elif sys.platform == 'darwin':
        # macOS
        base = Path.home() / 'Library' / 'Application Support'
        return base / 'aprimo_dam_audit' / 'native_host_manifest.json'
    else:
        # Linux
        base = Path.home() / '.config'
        return base / 'aprimo_dam_audit' / 'native_host_manifest.json'


def get_native_host_path():
    """Get the absolute path to native_host.py"""
    script_dir = Path(__file__).parent.resolve()
    return script_dir / 'native_host.py'


def create_manifest(extension_id: str, python_path: str = None):
    """Create native messaging host manifest"""
    
    if python_path is None:
        # Use current Python interpreter
        python_path = sys.executable
    
    # Get absolute path to native_host.py
    native_host_path = get_native_host_path()
    
    if not native_host_path.exists():
        print(f"Error: native_host.py not found at {native_host_path}")
        return None
    
    # Convert to absolute path string with forward slashes (works on all platforms)
    native_host_str = str(native_host_path.resolve()).replace('\\', '/')
    python_str = str(Path(python_path).resolve()).replace('\\', '/')
    
    manifest = {
        "name": "com.aprimo.dam_audit",
        "description": "Aprimo DAM Audit Native Host",
        "path": native_host_str,
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{extension_id}/"
        ]
    }
    
    # On Windows, we need to create a .bat wrapper
    if sys.platform == 'win32':
        bat_path = native_host_path.with_suffix('.bat')
        with open(bat_path, 'w') as f:
            f.write(f'@echo off\n')
            f.write(f'"{python_str}" "{native_host_str}" %*\n')
        
        manifest["path"] = str(bat_path.resolve()).replace('\\', '/')
        print(f"Created wrapper script: {bat_path}")
    
    return manifest


def install_manifest_windows(manifest_path: Path, manifest: dict):
    """Install manifest on Windows (creates registry key)"""
    import winreg
    
    # Create manifest directory
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write manifest file
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    # Create registry key
    reg_path = r"Software\Google\Chrome\NativeMessagingHosts\com.aprimo.dam_audit"
    
    try:
        # Create/open the registry key
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
        
        # Set the default value to the manifest path
        winreg.SetValue(key, "", winreg.REG_SZ, str(manifest_path))
        
        winreg.CloseKey(key)
        print(f"✓ Registry key created: HKCU\\{reg_path}")
        print(f"✓ Manifest path: {manifest_path}")
        return True
    except Exception as e:
        print(f"✗ Failed to create registry key: {e}")
        return False


def install_manifest_unix(manifest_path: Path, manifest: dict):
    """Install manifest on macOS/Linux"""
    # Create manifest directory
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write manifest file
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    # Make native_host.py executable
    native_host_path = Path(manifest["path"])
    if native_host_path.suffix == '.py':
        os.chmod(native_host_path, 0o755)
    
    print(f"✓ Manifest created: {manifest_path}")
    return True


def uninstall():
    """Remove native messaging host configuration"""
    manifest_path = get_manifest_path()
    
    if sys.platform == 'win32':
        # Remove registry key
        import winreg
        reg_path = r"Software\Google\Chrome\NativeMessagingHosts\com.aprimo.dam_audit"
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_path)
            print(f"✓ Removed registry key")
        except FileNotFoundError:
            print("ℹ Registry key not found (already removed?)")
        except Exception as e:
            print(f"✗ Failed to remove registry key: {e}")
    
    # Remove manifest file
    if manifest_path.exists():
        manifest_path.unlink()
        print(f"✓ Removed manifest: {manifest_path}")
        
        # Try to remove parent directory if empty
        try:
            manifest_path.parent.rmdir()
        except OSError:
            pass
    else:
        print(f"ℹ Manifest not found: {manifest_path}")


def verify_installation(extension_id: str):
    """Verify native messaging host is properly configured"""
    print("\nVerifying installation...")
    
    manifest_path = get_manifest_path()
    
    # Check manifest file exists
    if not manifest_path.exists():
        print(f"✗ Manifest file not found: {manifest_path}")
        return False
    
    print(f"✓ Manifest file exists: {manifest_path}")
    
    # Check manifest is valid JSON
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        print(f"✓ Manifest is valid JSON")
    except Exception as e:
        print(f"✗ Manifest is invalid: {e}")
        return False
    
    # Check native host script exists
    native_host_path = Path(manifest.get('path', ''))
    if not native_host_path.exists():
        print(f"✗ Native host script not found: {native_host_path}")
        return False
    
    print(f"✓ Native host script exists: {native_host_path}")
    
    # Check extension ID matches
    allowed_origins = manifest.get('allowed_origins', [])
    expected_origin = f"chrome-extension://{extension_id}/"
    if expected_origin in allowed_origins:
        print(f"✓ Extension ID matches: {extension_id}")
    else:
        print(f"✗ Extension ID mismatch")
        print(f"  Expected: {expected_origin}")
        print(f"  Found: {allowed_origins}")
        return False
    
    # On Windows, check registry
    if sys.platform == 'win32':
        import winreg
        reg_path = r"Software\Google\Chrome\NativeMessagingHosts\com.aprimo.dam_audit"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path)
            value = winreg.QueryValue(key, "")
            winreg.CloseKey(key)
            
            if Path(value) == manifest_path:
                print(f"✓ Registry key points to manifest")
            else:
                print(f"⚠ Registry key points to different manifest:")
                print(f"  Registry: {value}")
                print(f"  Expected: {manifest_path}")
        except FileNotFoundError:
            print(f"✗ Registry key not found: HKCU\\{reg_path}")
            return False
    
    print("\n✅ Native messaging host is properly configured!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Install native messaging host for Aprimo DAM Audit Extension"
    )
    parser.add_argument(
        '--extension-id',
        required=False,
        help='Chrome extension ID (from chrome://extensions)'
    )
    parser.add_argument(
        '--python',
        help='Path to Python interpreter (default: current Python)'
    )
    parser.add_argument(
        '--uninstall',
        action='store_true',
        help='Uninstall native messaging host'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify installation without installing'
    )
    
    args = parser.parse_args()
    
    # Uninstall mode
    if args.uninstall:
        print("Uninstalling native messaging host...")
        uninstall()
        return
    
    # Verify mode
    if args.verify:
        if not args.extension_id:
            print("Error: --extension-id required for verification")
            sys.exit(1)
        
        success = verify_installation(args.extension_id)
        sys.exit(0 if success else 1)
    
    # Install mode
    if not args.extension_id:
        print("Error: --extension-id is required")
        print("\nTo get your extension ID:")
        print("  1. Open chrome://extensions")
        print("  2. Enable 'Developer mode' (top-right toggle)")
        print("  3. Find your extension in the list")
        print("  4. Copy the ID shown (e.g., mgpfabhbihecophkkeiphcmjkeilafpf)")
        print("\nThen run:")
        print(f"  python {sys.argv[0]} --extension-id YOUR_EXTENSION_ID")
        sys.exit(1)
    
    print(f"Installing native messaging host...")
    print(f"Extension ID: {args.extension_id}")
    print(f"Platform: {sys.platform}")
    
    # Create manifest
    manifest = create_manifest(args.extension_id, args.python)
    if manifest is None:
        sys.exit(1)
    
    # Get manifest path
    manifest_path = get_manifest_path()
    print(f"Manifest location: {manifest_path}")
    
    # Install based on platform
    if sys.platform == 'win32':
        success = install_manifest_windows(manifest_path, manifest)
    else:
        success = install_manifest_unix(manifest_path, manifest)
    
    if success:
        print("\n✅ Native messaging host installed successfully!")
        print("\nNext steps:")
        print("  1. Reload the extension in chrome://extensions")
        print("  2. Test by clicking the extension icon")
        print("  3. Click 'Run Audit Pipeline' button")
        
        # Verify installation
        verify_installation(args.extension_id)
    else:
        print("\n✗ Installation failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
