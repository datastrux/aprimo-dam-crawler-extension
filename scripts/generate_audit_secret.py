#!/usr/bin/env python3
"""Generate shared secret for HMAC signature verification between extension and native host."""

import secrets
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_FILE = ROOT / ".audit_secret"


def generate_secret() -> bytes:
    """Generate a cryptographically secure random secret (32 bytes = 256 bits)."""
    return secrets.token_bytes(32)


def main() -> None:
    # Generate secret
    secret = generate_secret()
    
    # Write to file
    SECRET_FILE.write_bytes(secret)
    
    # Set file permissions (Unix-like systems only)
    if os.name != 'nt':  # Not Windows
        try:
            SECRET_FILE.chmod(0o600)  # Read/write for owner only
        except Exception:
            pass  # Ignore permission errors
    
    # Output hex-encoded secret for extension storage
    hex_secret = secret.hex()
    
    print(f"✅ Secret generated and saved to: {SECRET_FILE}")
    print()
    print(f"🔐 Secret (hex): {hex_secret}")
    print()
    print("📝 Next step: Store in Chrome extension")
    print()
    print("In Chrome DevTools (Service Worker console at chrome://extensions), run:")
    print()
    print("chrome.storage.local.set({")
    print(f"  'auditSecretKey': '{hex_secret}'")
    print("}, () => console.log('✅ Secret stored'));")
    print()
    print("Then reload the extension and run the audit pipeline.")
    print()
    print("🔒 Security note:")
    print("   - Keep this secret safe and never commit to version control")
    print("   - Both .audit_secret and .gitignore protect this file")


if __name__ == "__main__":
    main()
