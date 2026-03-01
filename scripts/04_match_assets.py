from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import imagehash

from audit_common import AUDIT_DIR, ensure_dirs, load_json, write_json


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

    dam_by_sha: dict[str, list[dict]] = defaultdict(list)
    dam_ok_rows = [x for x in dam_rows if x.get("fingerprint_status") == "ok"]
    for row in dam_ok_rows:
        sha = row.get("sha256")
        if sha:
            dam_by_sha[sha].append(row)

    matches: list[dict] = []
    unmatched: list[dict] = []

    for row in citizens_rows:
        if row.get("fingerprint_status") != "ok":
            unmatched.append({
                **row,
                "match_status": "unmatched_error",
                "match_reason": row.get("fingerprint_error") or "citizens_fingerprint_error",
            })
            continue

        sha = row.get("sha256")
        phash = row.get("phash")

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
                })
            continue

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
            })
        else:
            unmatched.append({
                **row,
                "match_status": "unmatched",
                "match_reason": "no_dam_match",
                "best_phash_distance": best_dist,
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

    write_json(AUDIT_DIR / "match_results.json", matches)
    write_json(AUDIT_DIR / "unmatched_results.json", unmatched)
    write_json(AUDIT_DIR / "dam_internal_dupes.json", dam_dupes_by_sha)

    print(json.dumps({
        "citizens_rows": len(citizens_rows),
        "matches": len(matches),
        "unmatched": len(unmatched),
        "dam_internal_dupe_groups": len(dam_dupes_by_sha),
        "outputs": {
            "matches": str(AUDIT_DIR / "match_results.json"),
            "unmatched": str(AUDIT_DIR / "unmatched_results.json"),
            "dam_dupes": str(AUDIT_DIR / "dam_internal_dupes.json"),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
