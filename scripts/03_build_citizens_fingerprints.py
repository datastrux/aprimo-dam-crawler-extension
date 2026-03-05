from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import imagehash
import requests
import urllib3
from PIL import Image

# Disable SSL warnings for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from audit_common import (
    AUDIT_DIR,
    CITIZENS_FINGERPRINTS_SCHEMA,
    decompress_citizens_images,
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
PROGRESS_PREFIX = "AUDIT_PROGRESS "


def emit_progress(current: int, total: int, message: str) -> None:
    """Emit structured progress for extension UI"""
    percent = round((current / total) * 100, 2) if total > 0 else 0
    payload = {
        "stage": "03_build_citizens_fingerprints.py",
        "current": current,
        "total": total,
        "percent": percent,
        "message": message,
        # Aliases for popup rendering
        "images_processed": current,
        "images_total": total,
    }
    print(f"{PROGRESS_PREFIX}{json.dumps(payload, ensure_ascii=False)}", flush=True)


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
        resp = requests.get(image_url, timeout=timeout, verify=False)
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


def process_images_in_chunks(image_index, timeout, workers, chunk_size=1000):
    """
    Process images in chunks to reduce memory usage.
    
    Instead of loading all fingerprints in memory, process in batches
    and yield results incrementally.
    """
    total_images = len(image_index)
    
    for chunk_start in range(0, total_images, chunk_size):
        chunk_end = min(chunk_start + chunk_size, total_images)
        chunk = image_index[chunk_start:chunk_end]
        
        print(f"Processing chunk {chunk_start:,}-{chunk_end:,} of {total_images:,}...")
        
        # Process this chunk in parallel
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(process_single_image, entry, timeout): entry
                for entry in chunk
            }
            
            for future in as_completed(futures):
                try:
                    yield future.result()
                except Exception as exc:
                    print(f"Image processing error: {exc}")
                    # Still yield a failed entry
                    entry = futures[future]
                    yield {
                        "image_url": entry.get("image_url", ""),
                        "fingerprint_status": "error",
                        "fingerprint_error": str(exc)
                    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fingerprints for Citizens-served images")
    parser.add_argument("--images-json", type=Path, default=AUDIT_DIR / "citizens_images_index.json")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Number of parallel workers")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Process images in chunks (reduces memory)")
    args = parser.parse_args()

    ensure_dirs()
    
    # Load and decompress index
    print("Loading citizens images index...")
    compressed_data = load_json(args.images_json)
    image_index = decompress_citizens_images(compressed_data)
    total_images = len(image_index)
    
    print(f"✓ Loaded {total_images:,} images (decompressed)")
    print(f"Processing with {args.workers} parallel workers in chunks of {args.chunk_size}...")
    
    emit_progress(0, total_images, "Starting Citizens image fingerprinting")

    rows: list[dict] = []
    completed = 0
    
    # Process images in chunks to reduce memory usage
    for row in process_images_in_chunks(image_index, args.timeout, args.workers, args.chunk_size):
        rows.append(row)
        completed += 1
        
        # Progress reporting every 50 images (more frequent for UI responsiveness)
        if completed % 50 == 0:
            emit_progress(completed, total_images, f"Fingerprinted {completed:,}/{total_images:,} Citizens images")
    
    # Final progress
    emit_progress(total_images, total_images, "Citizens image fingerprinting complete")
    
    # Clear image_index from memory (no longer needed)
    del image_index
    del compressed_data

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
