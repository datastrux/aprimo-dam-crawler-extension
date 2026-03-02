#!/usr/bin/env python3
"""Test domain whitelist validation with wildcard support."""

from audit_common import validate_url_domain

# Test cases: (url, expected_result, description)
test_cases = [
    # Citizens Bank domains
    ("https://www.citizensbank.com/page", True, "WWW subdomain"),
    ("https://citizensbank.com/page", True, "Base domain"),
    ("https://online.citizensbank.com/login", True, "Online subdomain"),
    ("https://mobile.citizensbank.com/app", True, "Mobile subdomain"),
    ("https://new.citizensbank.com/page", True, "New subdomain (via wildcard)"),
    ("https://api.citizensbank.com/v1", True, "API subdomain (via wildcard)"),
    
    # Aprimo domains
    ("https://aprimo.com/dam/123", True, "Aprimo base domain"),
    ("https://dam.aprimo.com/asset/456", True, "DAM subdomain (via wildcard)"),
    ("https://cdn.aprimo.com/image.jpg", True, "CDN subdomain (via wildcard)"),
    ("https://r1.previews.aprimo.com/thumb.jpg", True, "R1 previews exact match"),
    ("https://r2.previews.aprimo.com/thumb.jpg", True, "R2 previews (via wildcard)"),
    ("https://previews.aprimo.com/thumb.jpg", True, "Previews base domain"),
    
    # Should be rejected
    ("https://evil.com/phishing", False, "Non-whitelisted domain"),
    ("https://citizensbank.evil.com/fake", False, "Look-alike domain"),
    ("https://fakeaprimo.com/scam", False, "Fake Aprimo"),
    ("http://192.168.1.1/admin", False, "IP address"),
    ("", False, "Empty URL"),
    
    # Edge cases
    ("https://www.citizensbank.com:8080/page", True, "With port number"),
    ("https://WWW.CITIZENSBANK.COM/PAGE", True, "Uppercase (should normalize)"),
]

def run_tests():
    print("🧪 Testing Domain Whitelist Validation\n")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for url, expected, description in test_cases:
        result = validate_url_domain(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} | {description}")
        print(f"       URL: {url}")
        print(f"       Expected: {expected}, Got: {result}")
        print()
    
    print("=" * 80)
    print(f"\n📊 Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    
    if failed > 0:
        print("❌ Some tests failed!")
        return 1
    else:
        print("✅ All tests passed!")
        return 0

if __name__ == "__main__":
    exit(run_tests())
