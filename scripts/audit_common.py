from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
AUDIT_DIR = ASSETS_DIR / "audit"
REPORTS_DIR = ROOT / "reports"

CITIZENS_URLS_PATH = ASSETS_DIR / "citizensbank_urls.txt"


def ensure_dirs() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def latest_dam_export() -> Path:
    candidates = sorted(ASSETS_DIR.glob("aprimo_dam_assets_master_*.json"))
    if not candidates:
        raise FileNotFoundError("No DAM export found in assets/ matching aprimo_dam_assets_master_*.json")
    return candidates[-1]


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        return url.strip()
    cleaned = parsed._replace(fragment="")
    return urlunparse(cleaned)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_url_list(path: Path) -> list[str]:
    urls: list[str] = []
    seen = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if not url or url.startswith("#"):
                continue
            normalized = normalize_url(url)
            if normalized in seen:
                continue
            seen.add(normalized)
            urls.append(normalized)
    return urls


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_join(base_url: str, maybe_relative: str) -> str:
    if not maybe_relative:
        return ""
    return normalize_url(urljoin(base_url, maybe_relative.strip()))


def allowed_image_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    disallowed = (".svg", ".eps")
    if path.endswith(disallowed):
        return False
    return True
