"""
Test script to verify that known matching images are correctly identified.

This test downloads and compares three pairs of images:
1. Citizens to DAM: 32112-CIA976x550-1.jpg vs Champions-in-Action-logo.png
2. DAM to DAM (duplicates): EBM_0919_Bolsover vs Bolsover_Kristen-1580.jpg

Run this on a machine with network access to both systems to verify
fingerprinting is working correctly.
"""

from __future__ import annotations

import sys
from io import BytesIO

import imagehash
import requests
import urllib3
from PIL import Image

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Test case 1: Citizens Bank to DAM match (Champions in Action logo)
TEST_CASE_1 = {
    "name": "Citizens to DAM: Champions in Action",
    "url1": "https://www.citizensbank.com/assets/CB_media/images/community/32112-CIA976x550-1.jpg",
    "url1_label": "Citizens Bank",
    "url2": "https://r1.previews.aprimo.com/citizensbank/2024/12/13_19/e830cf1a-fe3f-4725-ace9-b2450140d7b9_788796a1-3107-41bf-992b-e05960f84385_Prev.png",
    "url2_label": "DAM (Champions-in-Action-logo.png)",
}

# Test case 2: DAM to DAM duplicates (Bolsover images)
TEST_CASE_2 = {
    "name": "DAM to DAM: Bolsover Duplicates",
    "url1": "https://r1.previews.aprimo.com/citizensbank/2022/6/28_5/8576abac-4482-4eeb-a489-aec2005a6c80_7f9acd6a-cdf1-45d6-be55-38636499119a_Prev.jpg",
    "url1_label": "DAM (EBM_0919_Bolsover_E913901_1580.jpg)",
    "url2": "https://r1.previews.aprimo.com/citizensbank/2022/7/6_7/db8b6455-355b-41e3-a4eb-aeca0074c780_535d79ef-881d-4cb4-bbb9-88405c1f2243_Prev.jpg",
    "url2_label": "DAM (Bolsover_Kristen-1580.jpg)",
}

# All test cases
TEST_CASES = [TEST_CASE_1, TEST_CASE_2]

# Expected threshold for matching
DEFAULT_THRESHOLD = 8


def download_image(url: str, timeout: int = 20) -> bytes | None:
    """Download image from URL."""
    try:
        resp = requests.get(url, timeout=timeout, verify=False)
        if resp.ok:
            return resp.content
        else:
            print(f"❌ HTTP {resp.status_code} for {url}")
            return None
    except Exception as err:
        print(f"❌ Failed to download {url}: {err}")
        return None


def compute_phash(data: bytes) -> str | None:
    """Compute perceptual hash from image data."""
    try:
        with Image.open(BytesIO(data)) as img:
            return str(imagehash.phash(img))
    except Exception as err:
        print(f"❌ Failed to compute phash: {err}")
        return None


def test_image_pair(test_case: dict, threshold: int) -> tuple[bool, int | None]:
    """
    Test a single image pair.
    
    Returns:
        (success: bool, distance: int | None)
        success=True if match at threshold, False if no match or error
    """
    print("=" * 70)
    print(f"TEST: {test_case['name']}")
    print("=" * 70)
    print()
    
    # Download first image
    print(f"📥 Downloading {test_case['url1_label']}...")
    print(f"   {test_case['url1']}")
    data1 = download_image(test_case['url1'])
    if not data1:
        print(f"❌ Could not download {test_case['url1_label']}")
        return False, None
    
    phash1 = compute_phash(data1)
    if not phash1:
        print(f"❌ Could not compute phash for {test_case['url1_label']}")
        return False, None
    
    print(f"   ✓ phash: {phash1}")
    print()
    
    # Download second image
    print(f"📥 Downloading {test_case['url2_label']}...")
    print(f"   {test_case['url2']}")
    data2 = download_image(test_case['url2'])
    if not data2:
        print(f"❌ Could not download {test_case['url2_label']}")
        return False, None
    
    phash2 = compute_phash(data2)
    if not phash2:
        print(f"❌ Could not compute phash for {test_case['url2_label']}")
        return False, None
    
    print(f"   ✓ phash: {phash2}")
    print()
    
    # Compare hashes
    print("🔍 Comparing perceptual hashes...")
    try:
        hash1 = imagehash.hex_to_hash(phash1)
        hash2 = imagehash.hex_to_hash(phash2)
        distance = hash1 - hash2
    except Exception as err:
        print(f"❌ Could not compare hashes: {err}")
        return False, None
    
    print(f"   Hamming distance: {distance}")
    print()
    
    # Evaluate against thresholds
    print("📊 Threshold Analysis:")
    thresholds = [5, 8, 10, 12, 15]
    for t in thresholds:
        match = "✓ MATCH" if distance <= t else "✗ no match"
        current = " (current default)" if t == threshold else ""
        print(f"   Threshold {t:2d}: {match}{current}")
    print()
    
    # Result for this test
    if distance <= threshold:
        print(f"✅ PASS: Images match (distance {distance} <= threshold {threshold})")
        return True, distance
    else:
        print(f"⚠️  WARNING: Images DO NOT match at threshold {threshold}")
        print(f"   Distance: {distance}")
        print(f"   Recommendation: Increase threshold to at least {distance}")
        return False, distance


def main() -> int:
    print("=" * 70)
    print("KNOWN MATCH TEST - Image Fingerprinting Verification")
    print("=" * 70)
    print(f"\nTesting {len(TEST_CASES)} image pairs with threshold {DEFAULT_THRESHOLD}\n")
    print()
    
    results = []
    for i, test_case in enumerate(TEST_CASES, 1):
        success, distance = test_image_pair(test_case, DEFAULT_THRESHOLD)
        results.append({
            "name": test_case["name"],
            "success": success,
            "distance": distance,
        })
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r["success"] and r["distance"] is not None)
    warnings = sum(1 for r in results if not r["success"] and r["distance"] is not None)
    failed = sum(1 for r in results if r["distance"] is None)
    
    for r in results:
        status = "✅ PASS" if r["success"] and r["distance"] is not None else \
                 "⚠️  WARN" if not r["success"] and r["distance"] is not None else \
                 "❌ FAIL"
        dist_str = f"distance={r['distance']}" if r["distance"] is not None else "error"
        print(f"{status} - {r['name']} ({dist_str})")
    
    print()
    print(f"Results: {passed} passed, {warnings} warnings, {failed} failed")
    print()
    
    # Recommendations
    if warnings > 0:
        max_distance = max((r["distance"] for r in results if r["distance"] is not None), default=DEFAULT_THRESHOLD)
        if max_distance > DEFAULT_THRESHOLD:
            print("📝 RECOMMENDATION:")
            print(f"   Increase phash threshold to at least {max_distance}")
            print(f"   Edit scripts/04_match_assets.py: --phash-threshold {max_distance}")
            print()
    
    # Exit code
    if failed > 0:
        print("=" * 70)
        print("❌ TEST FAILED - Errors downloading or fingerprinting images")
        print("=" * 70)
        return 1
    elif warnings > 0:
        print("=" * 70)
        print("⚠️  TEST WARNING - Threshold adjustment needed")
        print("=" * 70)
        return 2
    else:
        print("=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
