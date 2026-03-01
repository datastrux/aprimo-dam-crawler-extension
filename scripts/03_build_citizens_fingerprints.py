from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

import imagehash
import requests
from PIL import Image

from audit_common import AUDIT_DIR, ensure_dirs, load_json, normalize_url, sha256_bytes, write_json


def image_phash(data: bytes) -> str | None:
    try:
        with Image.open(BytesIO(data)) as image:
            return str(imagehash.phash(image))
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fingerprints for Citizens-served images")
    parser.add_argument("--images-json", type=Path, default=AUDIT_DIR / "citizens_images_index.json")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    ensure_dirs()
    image_index = load_json(args.images_json)

    rows: list[dict] = []
    for idx, entry in enumerate(image_index, start=1):
        image_url = normalize_url(entry.get("image_url") or "")
        if not image_url:
            continue

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
            resp = requests.get(image_url, timeout=args.timeout)
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

        rows.append(row)
        if idx % 250 == 0:
            print(f"Processed Citizens images: {idx}/{len(image_index)}")

    output = AUDIT_DIR / "citizens_fingerprints.json"
    write_json(output, rows)

    print(json.dumps({
        "rows": len(rows),
        "ok": sum(1 for r in rows if r["fingerprint_status"] == "ok"),
        "errors": sum(1 for r in rows if r["fingerprint_status"] == "error"),
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
