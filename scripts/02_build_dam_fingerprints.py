from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

import imagehash
import requests
from PIL import Image

from audit_common import AUDIT_DIR, ensure_dirs, latest_dam_export, load_json, normalize_url, sha256_bytes, write_json


def image_phash(data: bytes) -> str | None:
    try:
        with Image.open(BytesIO(data)) as image:
            return str(imagehash.phash(image))
    except Exception:
        return None


def build_fingerprints(dam_json: Path, timeout: int) -> list[dict]:
    payload = load_json(dam_json)
    assets = payload.get("assets", []) if isinstance(payload, dict) else payload

    rows: list[dict] = []
    for idx, asset in enumerate(assets, start=1):
        item_id = str(asset.get("itemId") or "").strip().lower()
        if not item_id:
            continue

        preview_url = normalize_url(asset.get("previewUrl") or "")
        file_type = str(asset.get("fileType") or "").lower()
        if file_type in {"svg", "eps"}:
            continue

        row = {
            "item_id": item_id,
            "file_name": asset.get("fileName"),
            "preview_url": preview_url,
            "file_type": file_type,
            "sha256": None,
            "phash": None,
            "fingerprint_status": "missing_preview",
            "fingerprint_error": None,
        }

        if preview_url:
            try:
                resp = requests.get(preview_url, timeout=timeout)
                if resp.ok:
                    data = resp.content
                    row["sha256"] = sha256_bytes(data)
                    row["phash"] = image_phash(data)
                    row["fingerprint_status"] = "ok" if row["sha256"] else "error"
                else:
                    row["fingerprint_status"] = "error"
                    row["fingerprint_error"] = f"HTTP_{resp.status_code}"
            except Exception as err:
                row["fingerprint_status"] = "error"
                row["fingerprint_error"] = str(err)

        rows.append(row)
        if idx % 250 == 0:
            print(f"Processed DAM assets: {idx}/{len(assets)}")

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DAM image fingerprints from exported DAM assets JSON")
    parser.add_argument("--dam-json", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    ensure_dirs()
    dam_json = args.dam_json or latest_dam_export()
    rows = build_fingerprints(dam_json, timeout=args.timeout)

    output = AUDIT_DIR / "dam_fingerprints.json"
    write_json(output, rows)

    print(json.dumps({
        "dam_json": str(dam_json),
        "rows": len(rows),
        "ok": sum(1 for r in rows if r["fingerprint_status"] == "ok"),
        "missing_preview": sum(1 for r in rows if r["fingerprint_status"] == "missing_preview"),
        "errors": sum(1 for r in rows if r["fingerprint_status"] == "error"),
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
