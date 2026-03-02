from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import imagehash

from audit_common import AUDIT_DIR, ensure_dirs, load_json, write_json


def extract_asset_id_from_url(url: str) -> str | None:
    """Extract Aprimo asset/item ID from CDN URL.
    
    Examples:
        - https://aprimo.com/dam/12345/hero.jpg → "12345"
        - https://r1.previews.aprimo.com/item/67890 → "67890"
        - https://www.citizensbank.com/local.jpg → None
    """
    if not url or "aprimo.com" not in url.lower():
        return None
    
    # Try pattern: /dam/{id}/ or /item/{id}
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


def phash_distance(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Match Citizens images to DAM assets")
    parser.add_argument("--citizens", type=Path, default=AUDIT_DIR / "citizens_fingerprints.json")
    parser.add_argument("--dam", type=Path, default=AUDIT_DIR / "dam_fingerprints.json")
    parser.add_argument("--phash-threshold", type=int, default=8)
    args = parser.parse_args()

    ensure_dirs()
    citizens_rows = load_json(args.citizens)
    dam_rows = load_json(args.dam)

    # Index DAM by SHA256 for exact matching
    dam_by_sha: dict[str, list[dict]] = defaultdict(list)
    dam_ok_rows = [x for x in dam_rows if x.get("fingerprint_status") == "ok"]
    for row in dam_ok_rows:
        sha = row.get("sha256")
        if sha:
            dam_by_sha[sha].append(row)
    
    # Index DAM by item_id for URL-based matching
    dam_by_item_id: dict[str, dict] = {}
    for row in dam_ok_rows:
        item_id = row.get("item_id")
        if item_id:
            dam_by_item_id[str(item_id)] = row

    matches: list[dict] = []
    unmatched: list[dict] = []

    for row in citizens_rows:
        if row.get("fingerprint_status") != "ok":
            unmatched.append({
                **row,
                "match_status": "unmatched_error",
                "match_reason": row.get("fingerprint_error") or "citizens_fingerprint_error",
                "url_contains_asset_id": False,
            })
            continue

        image_url = row.get("image_url", "")
        sha = row.get("sha256")
        phash = row.get("phash")
        
        # Step 1: Check if URL contains Aprimo asset ID (direct DAM usage)
        asset_id_from_url = extract_asset_id_from_url(image_url)
        url_match_found = False
        
        if asset_id_from_url and asset_id_from_url in dam_by_item_id:
            dam_record = dam_by_item_id[asset_id_from_url]
            matches.append({
                **row,
                "match_status": "match_url_direct",
                "dam_item_id": dam_record.get("item_id"),
                "dam_preview_url": dam_record.get("preview_url"),
                "dam_file_name": dam_record.get("file_name"),
                "phash_distance": 0,
                "url_contains_asset_id": True,
                "match_method": "url_asset_id",
            })
            url_match_found = True
            continue

        # Step 2: Try exact SHA256 match (perfect pixel match)
        exact_candidates = dam_by_sha.get(sha, []) if sha else []
        if exact_candidates:
            for candidate in exact_candidates:
                matches.append({
                    **row,
                    "match_status": "match_exact",
                    "dam_item_id": candidate.get("item_id"),
                    "dam_preview_url": candidate.get("preview_url"),
                    "dam_file_name": candidate.get("file_name"),
                    "phash_distance": 0,
                    "url_contains_asset_id": bool(asset_id_from_url),
                    "match_method": "sha256_exact",
                })
            continue

        # Step 3: Try perceptual hash (phash) matching for similar images
        best = None
        best_dist = None
        for candidate in dam_ok_rows:
            dist = phash_distance(phash, candidate.get("phash"))
            if dist is None:
                continue
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = candidate

        if best is not None and best_dist is not None and best_dist <= args.phash_threshold:
            matches.append({
                **row,
                "match_status": "match_phash",
                "dam_item_id": best.get("item_id"),
                "dam_preview_url": best.get("preview_url"),
                "dam_file_name": best.get("file_name"),
                "phash_distance": best_dist,
                "url_contains_asset_id": bool(asset_id_from_url),
                "match_method": "phash_similar",
            })
        else:
            unmatched.append({
                **row,
                "match_status": "unmatched",
                "match_reason": "no_dam_match",
                "best_phash_distance": best_dist,
                "url_contains_asset_id": bool(asset_id_from_url),
            })

    dam_dupes_by_sha = [
        {
            "sha256": sha,
            "count": len(rows),
            "item_ids": sorted({x.get("item_id") for x in rows if x.get("item_id")}),
            "file_names": sorted({x.get("file_name") for x in rows if x.get("file_name")}),
        }
        for sha, rows in dam_by_sha.items()
        if len(rows) > 1
    ]
    
    # Detect Citizens duplicates (same image served from multiple URLs)
    citizens_dupes_by_phash: dict[str, list[dict]] = defaultdict(list)
    for row in matches:
        phash = row.get("phash")
        if phash:
            citizens_dupes_by_phash[phash].append(row)
    
    citizens_duplicates = [
        {
            "phash": phash,
            "count": len(rows),
            "image_urls": [r.get("image_url") for r in rows],
            "dam_item_id": rows[0].get("dam_item_id") if rows else None,
            "total_page_count": sum(r.get("page_count", 0) for r in rows),
            "has_direct_dam_url": any(r.get("url_contains_asset_id") for r in rows),
            "has_local_copy": any(not r.get("url_contains_asset_id") for r in rows),
        }
        for phash, rows in citizens_dupes_by_phash.items()
        if len(rows) > 1
    ]
    
    # Calculate governance metrics
    total_matched = len(matches)
    direct_dam_urls = sum(1 for m in matches if m.get("url_contains_asset_id"))
    local_copies = total_matched - direct_dam_urls
    
    governance_metrics = {
        "total_matched_images": total_matched,
        "using_direct_dam_urls": direct_dam_urls,
        "using_local_copies": local_copies,
        "dam_url_adoption_rate": round(direct_dam_urls / total_matched * 100, 2) if total_matched > 0 else 0,
        "citizens_duplicate_groups": len(citizens_duplicates),
        "total_duplicate_urls": sum(d["count"] for d in citizens_duplicates) - len(citizens_duplicates),
    }

    write_json(AUDIT_DIR / "match_results.json", matches)
    write_json(AUDIT_DIR / "unmatched_results.json", unmatched)
    write_json(AUDIT_DIR / "dam_internal_dupes.json", dam_dupes_by_sha)
    write_json(AUDIT_DIR / "citizens_duplicates.json", citizens_duplicates)
    write_json(AUDIT_DIR / "governance_metrics.json", governance_metrics)

    print(json.dumps({
        "citizens_rows": len(citizens_rows),
        "matches": len(matches),
        "match_url_direct": sum(1 for m in matches if m.get("match_status") == "match_url_direct"),
        "match_exact": sum(1 for m in matches if m.get("match_status") == "match_exact"),
        "match_phash": sum(1 for m in matches if m.get("match_status") == "match_phash"),
        "unmatched": len(unmatched),
        "dam_internal_dupe_groups": len(dam_dupes_by_sha),
        "citizens_duplicate_groups": len(citizens_duplicates),
        "governance": governance_metrics,
        "outputs": {
            "matches": str(AUDIT_DIR / "match_results.json"),
            "unmatched": str(AUDIT_DIR / "unmatched_results.json"),
            "dam_dupes": str(AUDIT_DIR / "dam_internal_dupes.json"),
            "citizens_dupes": str(AUDIT_DIR / "citizens_duplicates.json"),
            "governance": str(AUDIT_DIR / "governance_metrics.json"),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
