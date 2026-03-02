#!/usr/bin/env python3
"""Test URL-based asset ID extraction and enhanced matching logic."""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from audit_common import validate_url_domain

# Import the function we're testing
import re

def extract_asset_id_from_url(url: str) -> str | None:
    """Extract Aprimo asset/item ID from CDN URL."""
    if not url or "aprimo.com" not in url.lower():
        return None
    
    patterns = [
        r'/dam/(\d+)/',
        r'/item/(\d+)',
        r'/items/(\d+)',
        r'/asset/(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


# Test cases: (url, expected_asset_id, description)
test_cases = [
    # Aprimo URLs with asset IDs
    ("https://aprimo.com/dam/12345/hero.jpg", "12345", "DAM path with asset ID"),
    ("https://dam.aprimo.com/asset/67890", "67890", "Asset path"),
    ("https://r1.previews.aprimo.com/item/54321", "54321", "Item  path"),
    ("https://cdn.aprimo.com/items/98765/thumb.jpg", "98765", "Items path"),
    ("https://APRIMO.COM/dam/11111/test.png", "11111", "Uppercase domain"),
    
    # URLs without asset IDs
    ("https://www.citizensbank.com/local-image.jpg", None, "Citizens Bank local file"),
    ("https://aprimo.com/homepage", None, "Aprimo but no asset ID"),
    ("https://example.com/dam/fake/image.jpg", None, "Non-Aprimo domain"),
    ("", None, "Empty URL"),
    (None, None, "None URL"),
    
    # Edge cases
    ("https://aprimo.com/dam/abc123/file.jpg", None, "Non-numeric ID (should fail)"),
    ("https://aprimo.com/dam/12345", None, "Missing trailing slash (should fail)"),
]


def run_tests():
    print("🧪 Testing Asset ID Extraction\n")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for url, expected, description in test_cases:
        try:
            result = extract_asset_id_from_url(url)
            status = "✅ PASS" if result == expected else "❌ FAIL"
            
            if result == expected:
                passed += 1
            else:
                failed += 1
            
            print(f"{status} | {description}")
            if url:
                print(f"       URL: {url}")
            print(f"       Expected: {expected}, Got: {result}")
            print()
        except Exception as e:
            failed += 1
            print(f"❌ FAIL | {description}")
            print(f"       URL: {url}")
            print(f"       Exception: {e}")
            print()
    
    print("=" * 80)
    print(f"\n📊 Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    
    # Test domain whitelist integration
    print("\n" + "=" * 80)
    print("🧪 Testing Domain Whitelist with Aprimo URLs\n")
    
    aprimo_urls = [
        ("https://aprimo.com/dam/123/img.jpg", True, "Aprimo base domain"),
        ("https://dam.aprimo.com/asset/456", True, "DAM subdomain"),
        ("https://r1.previews.aprimo.com/thumb.jpg", True, "Previews subdomain"),
        ("https://www.citizensbank.com/page", True, "Citizens Bank"),
        ("https://evil.com/fake", False, "Non-whitelisted"),
    ]
    
    whitelist_passed = 0
    whitelist_failed = 0
    
    for url, expected, description in aprimo_urls:
        result = validate_url_domain(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            whitelist_passed += 1
        else:
            whitelist_failed += 1
        
        print(f"{status} | {description}: {url}")
        print(f"       Expected: {expected}, Got: {result}\n")
    
    print("=" * 80)
    print(f"\n📊 Whitelist Results: {whitelist_passed} passed, {whitelist_failed} failed")
    
    total_failed = failed + whitelist_failed
    if total_failed > 0:
        print(f"\n❌ {total_failed} tests failed!")
        return 1
    else:
        print("\n✅ All tests passed!")
        return 0


if __name__ == "__main__":
    exit(run_tests())
