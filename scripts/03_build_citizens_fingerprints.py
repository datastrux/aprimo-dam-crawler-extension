from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import imagehash
import requests
from PIL import Image

from audit_common import (
    AUDIT_DIR,
    CITIZENS_FINGERPRINTS_SCHEMA,
    ensure_dirs,
    load_json,
    normalize_url,
    sha256_bytes,
    validate_stage_output,
    write_json,
)

# Number of parallel workers for fingerprinting
# Adjust based on CPU cores and network bandwidth
MAX_WORKERS = 8


def image_phash(data: bytes) -> str | None:
    try:
        with Image.open(BytesIO(data)) as image:
            return str(imagehash.phash(image))
    except Exception:
        return None


def process_single_image(entry: dict, timeout: int) -> dict:
    """Process a single image - downloads and generates fingerprints.
    
    This function is designed to be run in parallel via ThreadPoolExecutor.
    Returns a dict with all fingerprint data.
    """
    image_url = normalize_url(entry.get("image_url") or "")
    if not image_url:
        return {
            "image_url": "",
            "page_count": 0,
            "page_urls": [],
            "sha256": None,
            "phash": None,
            "fingerprint_status": "error",
            "fingerprint_error": "EMPTY_URL",
        }

    row = {
        "image_url": image_url,
        "page_count": entry.get("page_count", 0),
        "page_urls": entry.get("page_urls", []),
        "sha256": None,
        "phash": None,
        "fingerprint_status": "ok",
        "fingerprint_error": None,
    }

    try:
        resp = requests.get(image_url, timeout=timeout)
        if resp.ok:
            data = resp.content
            row["sha256"] = sha256_bytes(data)
            row["phash"] = image_phash(data)
            if row["sha256"] is None:
                row["fingerprint_status"] = "error"
                row["fingerprint_error"] = "NO_HASH"
        else:
            row["fingerprint_status"] = "error"
            row["fingerprint_error"] = f"HTTP_{resp.status_code}"
    except Exception as err:
        row["fingerprint_status"] = "error"
        row["fingerprint_error"] = str(err)

    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fingerprints for Citizens-served images")
    parser.add_argument("--images-json", type=Path, default=AUDIT_DIR / "citizens_images_index.json")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Number of parallel workers")
    args = parser.parse_args()

    ensure_dirs()
    image_index = load_json(args.images_json)
    total_images = len(image_index)

    print(f"Processing {total_images:,} images with {args.workers} parallel workers...")

    rows: list[dict] = []
    completed = 0
    
    # Process images in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        future_to_entry = {
            executor.submit(process_single_image, entry, args.timeout): entry
            for entry in image_index
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_entry):
            try:
                row = future.result()
                rows.append(row)
                completed += 1
                
                # Progress reporting every 250 images
                if completed % 250 == 0:
                    percent = (completed / total_images) * 100
                    print(f"Progress: {completed:,}/{total_images:,} ({percent:.1f}%)")
            except Exception as exc:
                # Handle any unexpected errors during processing
                print(f"Image processing generated an exception: {exc}")
                completed += 1

    output = AUDIT_DIR / "citizens_fingerprints.json"
    write_json(output, rows)

    print(json.dumps({
        "rows": len(rows),
        "ok": sum(1 for r in rows if r["fingerprint_status"] == "ok"),
        "errors": sum(1 for r in rows if r["fingerprint_status"] == "error"),
        "output": str(output),
    }, indent=2))

    # Validate output
    validate_stage_output(output, CITIZENS_FINGERPRINTS_SCHEMA, "citizens_fingerprints")


if __name__ == "__main__":
    main()
