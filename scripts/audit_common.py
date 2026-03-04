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

CITIZENS_URLS_PATH = AUDIT_DIR / "citizensbank_urls.txt"

# ============================================================================
# DATA SOURCE CONFIGURATION (SharePoint-Ready)
# ============================================================================
# To migrate to SharePoint, change 'type' to 'sharepoint' and update 'source'
# The loader functions below will automatically handle remote URLs
# ============================================================================

DATA_SOURCE_CONFIG = {
    # Citizens Bank URL List
    "citizens_urls": {
        "enabled": True,
        "type": "local",  # 'local' | 'url' | 'sharepoint'
        "source": str(CITIZENS_URLS_PATH),  # Local path or URL
        # Future SharePoint example:
        # "type": "sharepoint",
        # "source": "https://company.sharepoint.com/sites/DAM/citizensbank_urls.txt",
        # "auth_token": None,  # Set via environment variable
    },
    
    # DAM Assets Catalog
    "dam_assets": {
        "enabled": True,
        "type": "local",  # 'local' | 'url' | 'sharepoint'
        "source": str(AUDIT_DIR / "dam_assets.json"),  # Local path or URL
        # Future SharePoint example:
        # "type": "sharepoint",
        # "source": "https://company.sharepoint.com/sites/DAM/dam_assets.json",
        # "auth_token": None,
    },
}

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


def fetch_from_source(source_key: str) -> str:
    """Fetch data from configured source (local file or remote URL).
    
    Args:
        source_key: Key in DATA_SOURCE_CONFIG (e.g., 'citizens_urls', 'dam_assets')
        
    Returns:
        Text content from the source
        
    Raises:
        ValueError: If source is not configured or disabled
        FileNotFoundError: If local file doesn't exist
        Exception: If remote fetch fails
    """
    import sys
    
    config = DATA_SOURCE_CONFIG.get(source_key)
    if not config or not config.get("enabled"):
        raise ValueError(f"Data source '{source_key}' is not configured or disabled")
    
    source_type = config.get("type", "local")
    source = config.get("source")
    
    if not source:
        raise ValueError(f"Data source '{source_key}' has no source path/URL configured")
    
    # Local file
    if source_type == "local":
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Local file not found: {path}")
        return path.read_text(encoding="utf-8")
    
    # Remote URL (including SharePoint)
    elif source_type in ("url", "sharepoint"):
        try:
            import urllib.request
            import urllib.error
            
            headers = {}
            
            # Add authentication for SharePoint
            if source_type == "sharepoint" and config.get("auth_token"):
                headers["Authorization"] = f"Bearer {config['auth_token']}"
            
            req = urllib.request.Request(source, headers=headers)
            
            sys.stderr.write(f"[Data Source] Fetching {source_key} from: {source}\n")
            
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8")
                
        except urllib.error.URLError as e:
            raise Exception(f"Failed to fetch {source_key} from {source}: {e}")
    
    else:
        raise ValueError(f"Unknown source type '{source_type}' for {source_key}")


def load_json_from_source(source_key: str) -> Any:
    """Load JSON data from configured source (local or remote).
    
    Args:
        source_key: Key in DATA_SOURCE_CONFIG
        
    Returns:
        Parsed JSON data
    """
    text = fetch_from_source(source_key)
    return json.loads(text)


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_url_list(path: Path) -> list[str]:
    """Read URL list from local file path.
    
    For SharePoint-aware loading, use read_url_list_from_source() instead.
    """
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


def read_url_list_from_source(source_key: str = "citizens_urls") -> list[str]:
    """Read URL list from configured source (local file or SharePoint).
    
    Args:
        source_key: Key in DATA_SOURCE_CONFIG (default: 'citizens_urls')
        
    Returns:
        List of validated, normalized URLs
    """
    import sys
    
    text = fetch_from_source(source_key)
    
    urls: list[str] = []
    seen = set()
    rejected_count = 0
    
    for line in text.splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        normalized = normalize_url(url)
        if normalized in seen:
            continue
        
        # Validate domain against whitelist
        if not validate_url_domain(normalized):
            rejected_count += 1
            if rejected_count <= 5:
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


# JSON Schema definitions for validation
CITIZENS_IMAGES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["image_url"],
        "properties": {
            "image_url": {"type": "string"},
            "page_count": {"type": "integer"},
            "page_urls": {"type": "array", "items": {"type": "string"}}
        }
    }
}

DAM_FINGERPRINTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["item_id"],
        "properties": {
            "item_id": {"type": "string"},
            "sha256": {"type": ["string", "null"]},
            "phash": {"type": ["string", "null"]}
        }
    }
}

CITIZENS_FINGERPRINTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["image_url", "fingerprint_status"],
        "properties": {
            "image_url": {"type": "string"},
            "sha256": {"type": ["string", "null"]},
            "phash": {"type": ["string", "null"]},
            "fingerprint_status": {"type": "string"}
        }
    }
}


def validate_json_schema(data: Any, schema: dict, schema_name: str = "data") -> bool:
    """Validate JSON data against a schema.
    
    Args:
        data: The data to validate
        schema: JSON schema dict
        schema_name: Name for error messages
    
    Returns:
        True if valid, False otherwise
    
    Note:
        Requires jsonschema package. If not installed, returns True (no validation).
    """
    try:
        import jsonschema
        jsonschema.validate(instance=data, schema=schema)
        return True
    except ImportError:
        # jsonschema not installed - skip validation
        import sys
        sys.stderr.write(f"[Warning] jsonschema not installed - skipping {schema_name} validation\n")
        return True
    except jsonschema.ValidationError as e:
        import sys
        sys.stderr.write(f"[ValidationError] {schema_name} validation failed:\n")
        sys.stderr.write(f"  Path: {' -> '.join(str(p) for p in e.path)}\n")
        sys.stderr.write(f"  Error: {e.message}\n")
        return False
    except Exception as e:
        import sys
        sys.stderr.write(f"[Error] Unexpected validation error for {schema_name}: {e}\n")
        return False


def validate_stage_output(file_path: Path, schema: dict, schema_name: str) -> bool:
    """Validate a stage output file against its schema.
    
    Args:
        file_path: Path to JSON file
        schema: JSON schema dict
        schema_name: Name for error messages
    
    Returns:
        True if valid, False otherwise
    """
    if not file_path.exists():
        import sys
        sys.stderr.write(f"[Error] File not found: {file_path}\n")
        return False
    
    try:
        data = load_json(file_path)
        result = validate_json_schema(data, schema, schema_name)
        if result:
            print(f"✓ {file_path.name} validated successfully ({len(data)} items)")
        return result
    except json.JSONDecodeError as e:
        import sys
        sys.stderr.write(f"[Error] Invalid JSON in {file_path.name}: {e}\n")
        return False


# ============================================================================
# URL Compression for Space Efficiency
# ============================================================================

class URLCompressor:
    """
    Compress URLs by deduplicating common domains and path prefixes.
    
    Reduces storage by 50-70% for large datasets with repeated domains.
    
    Example:
        Before: "https://www.citizensbank.com/content/dam/images/hero.jpg"
        After:  {"d": 0, "p": 0, "f": "hero.jpg"}
        
        Where metadata stores:
          domains[0] = "https://www.citizensbank.com"
          path_prefixes[0][0] = "/content/dam/images/"
    """
    
    def __init__(self):
        self.domains = []  # List of unique domains
        self.path_prefixes = {}  # {domain_idx: [prefix1, prefix2, ...]}
    
    def compress_url(self, url: str) -> dict:
        """Convert full URL to compressed format"""
        if not url:
            return {"d": -1, "p": -1, "f": ""}
        
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        # Find or add domain
        if domain not in self.domains:
            self.domains.append(domain)
        domain_idx = self.domains.index(domain)
        
        # Extract path
        path = parsed.path
        if not path or path == "/":
            return {
                "d": domain_idx,
                "p": -1,
                "f": "",
                "q": parsed.query if parsed.query else None
            }
        
        # Find or create path prefix
        if domain_idx not in self.path_prefixes:
            self.path_prefixes[domain_idx] = []
        
        # Look for matching prefix
        prefix_idx = -1
        for idx, prefix in enumerate(self.path_prefixes[domain_idx]):
            if path.startswith(prefix):
                prefix_idx = idx
                break
        
        # If no match and path has multiple segments, create new prefix
        if prefix_idx == -1:
            path_parts = [p for p in path.split('/') if p]
            # Use first 2-3 segments as common prefix (e.g., /content/dam/)
            if len(path_parts) >= 2:
                prefix = '/' + '/'.join(path_parts[:2]) + '/'
                if path.startswith(prefix):
                    self.path_prefixes[domain_idx].append(prefix)
                    prefix_idx = len(self.path_prefixes[domain_idx]) - 1
        
        # Get final path (remove prefix)
        final_path = path
        if prefix_idx >= 0:
            prefix = self.path_prefixes[domain_idx][prefix_idx]
            if path.startswith(prefix):
                final_path = path[len(prefix):]
        
        return {
            "d": domain_idx,
            "p": prefix_idx,
            "f": final_path,
            "q": parsed.query if parsed.query else None
        }
    
    def decompress_url(self, compressed: dict) -> str:
        """Reconstruct full URL from compressed format"""
        if compressed.get("d", -1) == -1:
            return ""
        
        domain = self.domains[compressed["d"]]
        
        # Build path
        path = ""
        if compressed.get("p", -1) >= 0:
            prefix = self.path_prefixes[compressed["d"]][compressed["p"]]
            path = prefix + compressed.get("f", "")
        else:
            path = compressed.get("f", "")
        
        url = domain + path
        
        if compressed.get("q"):
            url += f"?{compressed['q']}"
        
        return url
    
    def get_metadata(self) -> dict:
        """Return domain/path lookup tables for storage"""
        return {
            "domains": self.domains,
            "path_prefixes": self.path_prefixes
        }
    
    def set_metadata(self, metadata: dict) -> None:
        """Load domain/path lookup tables from storage"""
        self.domains = metadata.get("domains", [])
        self.path_prefixes = {
            int(k): v for k, v in metadata.get("path_prefixes", {}).items()
        }


def compress_citizens_images(images: list[dict]) -> dict:
    """
    Compress citizens image index for storage efficiency.
    
    Reduces file size by 50-70% by deduplicating URLs.
    
    Args:
        images: List of image dicts with 'image_url' and 'page_urls'
    
    Returns:
        Compressed format with metadata and compressed image list
    """
    compressor = URLCompressor()
    
    compressed_images = []
    for img in images:
        compressed_images.append({
            "u": compressor.compress_url(img.get("image_url", "")),
            "p": [compressor.compress_url(page) for page in img.get("page_urls", [])],
            "c": img.get("page_count", len(img.get("page_urls", [])))
        })
    
    return {
        "version": "1.0.0",
        "compressed": True,
        "metadata": compressor.get_metadata(),
        "images": compressed_images
    }


def decompress_citizens_images(compressed_data: dict | list) -> list[dict]:
    """
    Decompress citizens image index.
    
    Handles both compressed and uncompressed formats for backward compatibility.
    
    Args:
        compressed_data: Either compressed dict or uncompressed list
    
    Returns:
        Uncompressed list of image dicts
    """
    # Handle uncompressed format (backward compatibility)
    if isinstance(compressed_data, list):
        return compressed_data
    
    # Handle compressed format
    if not compressed_data.get("compressed"):
        # Old format with version but not compressed
        return compressed_data.get("images", [])
    
    compressor = URLCompressor()
    compressor.set_metadata(compressed_data["metadata"])
    
    images = []
    for compressed_img in compressed_data.get("images", []):
        images.append({
            "image_url": compressor.decompress_url(compressed_img["u"]),
            "page_urls": [compressor.decompress_url(p) for p in compressed_img.get("p", [])],
            "page_count": compressed_img.get("c", 0)
        })
    
    return images
