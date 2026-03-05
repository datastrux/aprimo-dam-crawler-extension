#!/usr/bin/env python3
"""
Diagnose why two images aren't matching in the audit pipeline.
Compare their fingerprints and show the hamming distance.
"""

import argparse
import sys
from io import BytesIO

import imagehash
import requests
from PIL import Image


def download_image(url: str, timeout: int = 20) -> bytes | None:
    """Download image from URL"""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"❌ Failed to download {url}: {e}")
        return None


def compute_phash(data: bytes) -> str | None:
    """Compute perceptual hash"""
    try:
        with Image.open(BytesIO(data)) as img:
            print(f"  Image size: {img.size}, mode: {img.mode}")
            return str(imagehash.phash(img))
    except Exception as e:
        print(f"  ❌ Failed to compute phash: {e}")
        return None


def compute_distance(hash1: str, hash2: str) -> int:
    """Compute hamming distance between two hashes"""
    h1 = imagehash.hex_to_hash(hash1)
    h2 = imagehash.hex_to_hash(hash2)
    return h1 - h2


def main():
    parser = argparse.ArgumentParser(description="Diagnose image matching issues")
    parser.add_argument("url1", help="First image URL (e.g., Citizens Bank)")
    parser.add_argument("url2", help="Second image URL (e.g., DAM preview)")
    parser.add_argument("--threshold", type=int, default=8, help="Current phash threshold (default: 8)")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print("IMAGE MATCHING DIAGNOSTIC")
    print(f"{'='*70}\n")

    print(f"Image 1: {args.url1}")
    data1 = download_image(args.url1)
    if not data1:
        sys.exit(1)
    phash1 = compute_phash(data1)
    if not phash1:
        sys.exit(1)
    print(f"  ✓ Perceptual hash: {phash1}\n")

    print(f"Image 2: {args.url2}")
    data2 = download_image(args.url2)
    if not data2:
        sys.exit(1)
    phash2 = compute_phash(data2)
    if not phash2:
        sys.exit(1)
    print(f"  ✓ Perceptual hash: {phash2}\n")

    distance = compute_distance(phash1, phash2)
    
    print(f"{'='*70}")
    print(f"RESULTS:")
    print(f"{'='*70}")
    print(f"Hamming distance: {distance}")
    print(f"Current threshold: {args.threshold}")
    
    if distance == 0:
        print("✅ EXACT MATCH - Hashes are identical")
    elif distance <= args.threshold:
        print(f"✅ MATCH - Distance {distance} is within threshold {args.threshold}")
    else:
        print(f"❌ NO MATCH - Distance {distance} exceeds threshold {args.threshold}")
        print(f"\nRECOMMENDATION:")
        print(f"  To match these images, increase threshold to at least {distance}")
        print(f"  Run pipeline with: python scripts/04_match_assets.py --phash-threshold {distance + 2}")
    
    print()


if __name__ == "__main__":
    main()
