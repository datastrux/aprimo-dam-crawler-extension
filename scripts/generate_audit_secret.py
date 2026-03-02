#!/usr/bin/env python3
"""Generate shared secret for HMAC signature verification between extension and native host."""

import secrets
import sys
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
    SECRET_FILE.chmod(0o600)  # Read/write for owner only
    
    # Output hex-encoded secret for extension storage
    hex_secret = secret.hex()
    
    print(f"✅ Secret generated and saved to: {SECRET_FILE}")
    print(f"📋 Add this to extension's encrypted storage:")
    print(f"{{")
    print(f'  "auditSecretKey": "{hex_secret}"')
    print(f"}}")
    print()
    print(f"🔐 Secret (hex): {hex_secret}")
    print()
    print("📝 Next steps:")
    print("1. Copy the hex secret above")
    print("2. Open chrome://extensions")
    print("3. Click 'Service Worker' for this extension")
    print("4. Run in console:")
    print(f'   // Import encrypted storage')
    print(f'   const {{ encryptedStorage }} = await import(chrome.runtime.getURL("encrypted_storage.js"));')
    print(f'   // Store secret in encrypted storage')
    print(f'   await encryptedStorage.set({{ auditSecretKey: "{hex_secret}" }});')
    print(f'   console.log("✅ Secret stored in encrypted storage");')
    print("5. Reload the extension")
    print()
    print("🔒 Security notes:")
    print("   - Secret is stored in encrypted form using AES-GCM")
    print("   - Secret file (.audit_secret) has owner-only permissions (600)")
    print("   - Keep this secret safe and never commit to version control")


if __name__ == "__main__":
    main()
