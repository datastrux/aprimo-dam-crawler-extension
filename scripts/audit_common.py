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

# Domain whitelist for security
# Only URLs from these domains will be processed
# Supports exact matches and wildcard patterns (*.domain.com)
ALLOWED_DOMAINS = {
    # Citizens Bank domains
    "citizensbank.com",
    "www.citizensbank.com",
    "online.citizensbank.com",
    "mobile.citizensbank.com",
    "*.citizensbank.com",  # Any Citizens Bank subdomain
    
    # Aprimo DAM domains (for embedded images)
    "aprimo.com",
    "*.aprimo.com",  # Any Aprimo subdomain (dam., cdn., etc.)
    "r1.previews.aprimo.com",
    "previews.aprimo.com",
    "*.previews.aprimo.com"
}


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


def validate_url_domain(url: str) -> bool:
    """Validate that URL is from an allowed domain.
    
    Supports exact domain matching and wildcard patterns (*.domain.com).
    Returns False for URLs from non-whitelisted domains to prevent processing
    of potentially malicious or unexpected URLs.
    
    Examples:
        - "citizensbank.com" matches exactly
        - "*.aprimo.com" matches "dam.aprimo.com", "cdn.aprimo.com", etc.
    """
    if not url:
        return False
    
    parsed = urlparse(url.strip())
    domain = parsed.netloc.lower()
    
    # Remove port if present
    if ':' in domain:
        domain = domain.split(':')[0]
    
    # Check exact match first (faster)
    if domain in ALLOWED_DOMAINS:
        return True
    
    # Check wildcard patterns (*.domain.com)
    for allowed in ALLOWED_DOMAINS:
        if allowed.startswith('*.'):
            # Wildcard pattern: *.aprimo.com matches dam.aprimo.com
            suffix = allowed[1:]  # Remove '*' to get '.aprimo.com'
            if domain.endswith(suffix):
                return True
            # Also match the base domain (aprimo.com matches *.aprimo.com)
            if domain == suffix[1:]:  # Remove leading '.'
                return True
    
    return False


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_url_list(path: Path) -> list[str]:
    import sys
    urls: list[str] = []
    seen = set()
    rejected_count = 0
    
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if not url or url.startswith("#"):
                continue
            normalized = normalize_url(url)
            if normalized in seen:
                continue
            
            # Validate domain against whitelist
            if not validate_url_domain(normalized):
                rejected_count += 1
                if rejected_count <= 5:  # Only log first 5 to avoid spam
                    sys.stderr.write(f"[Security] Rejected non-whitelisted URL: {normalized}\n")
                continue
            
            seen.add(normalized)
            urls.append(normalized)
    
    if rejected_count > 0:
        sys.stderr.write(f"[Security] Rejected {rejected_count} URLs from non-whitelisted domains\n")
    
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
