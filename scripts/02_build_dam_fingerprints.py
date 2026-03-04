from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

import imagehash
import requests
from PIL import Image

from audit_common import (
    AUDIT_DIR,
    DAM_FINGERPRINTS_SCHEMA,
    ensure_dirs,
    latest_dam_export,
    load_json,
    load_json_from_source,
    normalize_url,
    sha256_bytes,
    validate_stage_output,
    write_json,
)

PROGRESS_PREFIX = "AUDIT_PROGRESS "


def emit_progress(current: int, total: int, message: str) -> None:
    """Emit structured progress for extension UI"""
    percent = round((current / total) * 100, 2) if total > 0 else 0
    payload = {
        "stage": "02_build_dam_fingerprints.py",
        "current": current,
        "total": total,
        "percent": percent,
        "message": message,
        # Aliases for popup rendering
        "assets_processed": current,
        "assets_total": total,
    }
    print(f"{PROGRESS_PREFIX}{json.dumps(payload, ensure_ascii=False)}", flush=True)


def image_phash(data: bytes) -> str | None:
    try:
        with Image.open(BytesIO(data)) as image:
            return str(imagehash.phash(image))
    except Exception:
        return None


def build_fingerprints(assets_data: list | dict, timeout: int) -> list[dict]:
    """Build fingerprints from DAM assets data.
    
    Args:
        assets_data: Either a list of assets or dict with 'assets' key
        timeout: HTTP request timeout in seconds
    """
    assets = assets_data.get("assets", []) if isinstance(assets_data, dict) else assets_data
    total_assets = len(assets)
    
    print(f"Building fingerprints for {total_assets:,} DAM assets...")
    emit_progress(0, total_assets, "Starting DAM fingerprinting")

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
        
        # Emit progress every 50 assets (more frequent than 250)
        if idx % 50 == 0:
            emit_progress(idx, total_assets, f"Fingerprinted {idx:,}/{total_assets:,} DAM assets")

    # Final progress
    emit_progress(total_assets, total_assets, "DAM fingerprinting complete")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DAM image fingerprints from exported DAM assets JSON")
    parser.add_argument("--dam-json", type=Path, default=None, help="Path to DAM export JSON (local file)")
    parser.add_argument("--legacy", action="store_true", help="Use legacy file lookup instead of config (requires --dam-json or aprimo_dam_assets_master_*.json)")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    ensure_dirs()
    
    # Default: Use config-based loader (works with dam_assets.json from Phase 1)
    # Legacy: Use old file lookup for aprimo_dam_assets_master_*.json
    if args.legacy:
        dam_json = args.dam_json or latest_dam_export()
        assets_data = load_json(dam_json)
        dam_source = str(dam_json)
    else:
        print("[Config] Using data source from audit_common configuration...")
        assets_data = load_json_from_source("dam_assets")
        dam_source = "config: dam_assets.json"
    
    rows = build_fingerprints(assets_data, timeout=args.timeout)

    output = AUDIT_DIR / "dam_fingerprints.json"
    write_json(output, rows)

    print(json.dumps({
        "dam_source": dam_source,
        "rows": len(rows),
        "ok": sum(1 for r in rows if r["fingerprint_status"] == "ok"),
        "missing_preview": sum(1 for r in rows if r["fingerprint_status"] == "missing_preview"),
        "errors": sum(1 for r in rows if r["fingerprint_status"] == "error"),
        "output": str(output),
    }, indent=2))

    # Validate output
    validate_stage_output(output, DAM_FINGERPRINTS_SCHEMA, "dam_fingerprints")


if __name__ == "__main__":
    main()
