#!/usr/bin/env python3
"""
Quick diagnostic tool to test image discovery on a single URL.
Used to debug why the crawler isn't finding images.

Usage:
    python scripts/test_image_discovery.py https://www.citizensbank.com
    python scripts/test_image_discovery.py https://www.citizensbank.com/homepage --verbose
"""

import argparse
import sys
from pathlib import Path

# Add scripts directory to path so we can import audit_common
sys.path.insert(0, str(Path(__file__).parent))

import requests
from bs4 import BeautifulSoup
from audit_common import safe_join, allowed_image_extension
import re


def test_url(url: str, verbose: bool = False) -> None:
    """Test image discovery on a single URL"""
    
    print(f"\n{'='*70}")
    print(f"Testing Image Discovery on: {url}")
    print(f"{'='*70}\n")
    
    # Fetch the page
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        print("Fetching page...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"✓ HTTP {response.status_code} - {len(response.text)} bytes\n")
    except Exception as e:
        print(f"✗ Error fetching URL: {e}")
        return
    
    # Parse HTML
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find all <img> tags
    img_tags = soup.find_all("img")
    print(f"Found {len(img_tags)} <img> tags")
    
    if len(img_tags) == 0:
        print("⚠ WARNING: No <img> tags found on this page!")
        print("   This could mean:")
        print("   - The page uses JavaScript to load images (not visible to scraper)")
        print("   - The page has no images")
        print("   - The page structure is unusual")
        return
    
    # Analyze each image
    images_found = set()
    data_uri_count = 0
    rejected_extension = []
    no_src = 0
    
    print("\nAnalyzing image sources:\n")
    
    for i, img in enumerate(img_tags[:10], 1):  # Show first 10
        # Check all possible attributes
        attrs = {
            "src": img.get("src"),
            "data-src": img.get("data-src"),
            "data-lazy-src": img.get("data-lazy-src"),
            "data-original": img.get("data-original"),
            "data-srcset": img.get("data-srcset"),
            "data-lazy": img.get("data-lazy"),
            "data-raw": img.get("data-raw"),
            "srcset": img.get("srcset"),
        }
        
        if verbose:
            print(f"  Image #{i}:")
            for attr, value in attrs.items():
                if value:
                    display_value = value if len(value) < 80 else value[:77] + "..."
                    print(f"    {attr}: {display_value}")
        
        # Get the actual source
        src = (
            img.get("src") or 
            img.get("data-src") or 
            img.get("data-lazy-src") or 
            img.get("data-original") or
            img.get("data-srcset") or
            img.get("data-lazy") or
            img.get("data-raw")
        )
        
        if not src:
            no_src += 1
            if verbose:
                print(f"    → No source found\n")
            continue
        
        if src.startswith("data:"):
            data_uri_count += 1
            if verbose:
                print(f"    → Skipped (data URI)\n")
            continue
        
        # Resolve relative URLs
        resolved = safe_join(url, src)
        
        if not resolved:
            if verbose:
                print(f"    → Could not resolve URL\n")
            continue
        
        # Check if allowed
        if allowed_image_extension(resolved):
            images_found.add(resolved)
            if verbose:
                print(f"    ✓ ACCEPTED: {resolved}\n")
            else:
                print(f"  ✓ {resolved}")
        else:
            rejected_extension.append(resolved)
            if verbose:
                print(f"    ✗ REJECTED (extension): {resolved}\n")
    
    # Check <picture> <source> elements
    source_tags = soup.find_all("source")
    if source_tags:
        print(f"\nFound {len(source_tags)} <source> tags (HTML5 picture elements)")
        for source in source_tags[:5]:
            srcset = source.get("srcset") or source.get("data-srcset")
            if srcset and verbose:
                print(f"  source srcset: {srcset[:80]}...")
    
    # Check CSS background images
    style_urls = re.findall(r"url\((['\"]?)(.*?)\1\)", response.text, flags=re.IGNORECASE)
    if style_urls:
        print(f"\nFound {len(style_urls)} CSS url() references")
        if verbose:
            for i, (_, candidate) in enumerate(style_urls[:5], 1):
                resolved = safe_join(url, candidate)
                if resolved and allowed_image_extension(resolved):
                    images_found.add(resolved)
                    print(f"  ✓ CSS: {resolved}")
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Total <img> tags:        {len(img_tags)}")
    print(f"Images with no src:      {no_src}")
    print(f"Data URIs (skipped):     {data_uri_count}")
    print(f"Rejected (extension):    {len(rejected_extension)}")
    print(f"✓ ACCEPTED IMAGES:       {len(images_found)}")
    print(f"{'='*70}\n")
    
    if len(images_found) == 0:
        print("⚠ WARNING: Zero images discovered!")
        print("\nPossible reasons:")
        print("  1. All images are data URIs (embedded base64)")
        print("  2. All images are SVG/EPS (filtered by allowed_image_extension)")
        print("  3. Images use non-standard attributes (check --verbose output)")
        print("  4. Page uses JavaScript to dynamically load images")
        print("\nTry running with --verbose to see detailed attribute analysis.")
    else:
        print(f"✓ Successfully found {len(images_found)} images!")
        print("\nFirst 5 accepted images:")
        for img_url in list(images_found)[:5]:
            print(f"  {img_url}")
    
    if rejected_extension:
        print(f"\nRejected extensions ({len(rejected_extension)}):")
        for img_url in rejected_extension[:3]:
            print(f"  {img_url}")


def main():
    parser = argparse.ArgumentParser(description="Test image discovery on a single URL")
    parser.add_argument("url", help="URL to test (e.g., https://www.citizensbank.com)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed attribute analysis")
    args = parser.parse_args()
    
    test_url(args.url, verbose=args.verbose)


if __name__ == "__main__":
    main()
