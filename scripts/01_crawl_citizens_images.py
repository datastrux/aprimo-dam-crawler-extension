from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from audit_common import (
    AUDIT_DIR,
    CITIZENS_URLS_PATH,
    allowed_image_extension,
    ensure_dirs,
    normalize_url,
    read_url_list,
    safe_join,
    write_json,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

CHECKPOINT_PATH = AUDIT_DIR / "citizens_crawl_checkpoint.json"
CHECKPOINT_VERSION = 1
SAVE_EVERY_PAGES = 20
PROGRESS_PREFIX = "AUDIT_PROGRESS "


def emit_progress(
    current: int,
    total: int,
    message: str,
    resumed: bool,
    images_discovered: int = 0,
    images_pending: int = 0,
) -> None:
    percent = round((current / total) * 100, 2) if total > 0 else 0
    payload = {
        "stage": "01_crawl_citizens_images.py",
        "current": current,
        "total": total,
        "percent": percent,
        "message": message,
        "resumed": resumed,
        "images_discovered": images_discovered,
        "images_pending": images_pending,
        # Clearer aliases for popup rendering
        "urls_completed": current,
        "urls_total": total,
        "images_detected": images_discovered,
        "images_remaining": images_pending,
    }
    print(f"{PROGRESS_PREFIX}{json.dumps(payload, ensure_ascii=False)}", flush=True)


def load_checkpoint() -> tuple[set[str], list[dict], list[dict]]:
    if not CHECKPOINT_PATH.exists():
        return set(), [], []
    try:
        raw = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set(), [], []

    if raw.get("version") != CHECKPOINT_VERSION:
        return set(), [], []

    processed_urls = {normalize_url(x) for x in raw.get("processed_urls", []) if x}
    page_rows = raw.get("page_rows", [])
    image_rows = raw.get("image_rows", [])
    if not isinstance(page_rows, list) or not isinstance(image_rows, list):
        return set(), [], []

    return processed_urls, page_rows, image_rows


def save_checkpoint(total_urls: int, processed_urls: set[str], page_rows: list[dict], image_rows: list[dict]) -> None:
    write_json(
        CHECKPOINT_PATH,
        {
            "version": CHECKPOINT_VERSION,
            "total_urls": total_urls,
            "processed_urls": sorted(processed_urls),
            "page_rows": page_rows,
            "image_rows": image_rows,
        },
    )


def materialize_image_rows(image_key_set: set[tuple[str, str, str]]) -> list[dict]:
    return [
        {
            "page_url": page_url,
            "resolved_page_url": resolved_page_url,
            "image_url": image_url,
        }
        for page_url, resolved_page_url, image_url in sorted(image_key_set)
    ]


def parse_images_from_html(page_url: str, html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    images: set[str] = set()

    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            resolved = safe_join(page_url, src)
            if resolved and allowed_image_extension(resolved):
                images.add(resolved)

        srcset = img.get("srcset")
        if srcset:
            for part in srcset.split(","):
                candidate = part.strip().split(" ")[0]
                resolved = safe_join(page_url, candidate)
                if resolved and allowed_image_extension(resolved):
                    images.add(resolved)

    style_urls = re.findall(r"url\((['\"]?)(.*?)\1\)", html, flags=re.IGNORECASE)
    for _, candidate in style_urls:
        resolved = safe_join(page_url, candidate)
        if resolved and allowed_image_extension(resolved):
            images.add(resolved)

    return images


def crawl(urls: list[str], timeout: int, resume: bool) -> tuple[list[dict], list[dict], bool]:
    resumed = False
    if resume:
        processed_urls, page_rows, image_rows = load_checkpoint()
        resumed = len(processed_urls) > 0
    else:
        processed_urls, page_rows, image_rows = set(), [], []

    total_urls = len(urls)
    page_by_url: dict[str, dict] = {normalize_url(x.get("url", "")): x for x in page_rows if x.get("url")}
    image_key_set: set[tuple[str, str, str]] = {
        (x.get("page_url", ""), x.get("resolved_page_url", ""), x.get("image_url", ""))
        for x in image_rows
        if x.get("page_url") and x.get("resolved_page_url") and x.get("image_url")
    }

    emit_progress(
        current=len(processed_urls),
        total=total_urls,
        message="Resuming crawl from checkpoint" if resumed else "Starting crawl",
        resumed=resumed,
        images_discovered=len(image_key_set),
        images_pending=max(0, len(image_key_set)),
    )

    dirty_since_save = 0
    for idx, url in enumerate(urls, start=1):
        normalized_url = normalize_url(url)
        if normalized_url in processed_urls:
            continue

        row = {
            "url": url,
            "status": "ok",
            "http_status": None,
            "final_url": None,
            "redirect_count": 0,
            "redirect_hops": [],
            "error": None,
            "image_count": 0,
        }
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            row["http_status"] = resp.status_code
            row["final_url"] = normalize_url(resp.url)

            hops = []
            previous_url = url
            for hop in resp.history:
                hop_from = normalize_url(previous_url)
                hop_response_url = normalize_url(hop.url)
                location = hop.headers.get("Location")
                hop_to = normalize_url(safe_join(hop_response_url, location)) if location else hop_response_url
                hops.append(
                    {
                        "status_code": hop.status_code,
                        "from_url": hop_from,
                        "response_url": hop_response_url,
                        "location": location,
                        "to_url": hop_to,
                    }
                )
                previous_url = hop_to

            row["redirect_hops"] = hops
            row["redirect_count"] = len(hops)

            if not resp.ok:
                row["status"] = "error"
                row["error"] = f"HTTP_{resp.status_code}"
            else:
                final_url = normalize_url(resp.url)
                images = sorted(parse_images_from_html(final_url, resp.text))
                row["image_count"] = len(images)
                for image_url in images:
                    image_key_set.add((url, final_url, image_url))
        except Exception as err:
            row["status"] = "error"
            row["error"] = str(err)

        page_by_url[normalized_url] = row
        processed_urls.add(normalized_url)

        page_rows = list(page_by_url.values())

        dirty_since_save += 1
        processed_count = len(processed_urls)
        images_discovered = len(image_key_set)
        images_pending = max(0, images_discovered - processed_count)
        emit_progress(
            current=processed_count,
            total=total_urls,
            message=f"Crawled {processed_count}/{total_urls} pages",
            resumed=resumed,
            images_discovered=images_discovered,
            images_pending=images_pending,
        )

        if dirty_since_save >= SAVE_EVERY_PAGES:
            save_checkpoint(
                total_urls=total_urls,
                processed_urls=processed_urls,
                page_rows=page_rows,
                image_rows=materialize_image_rows(image_key_set),
            )
            dirty_since_save = 0

        if idx % 50 == 0:
            print(f"Crawled {processed_count}/{total_urls} pages...")

    page_rows = list(page_by_url.values())
    image_rows = materialize_image_rows(image_key_set)

    save_checkpoint(total_urls=total_urls, processed_urls=processed_urls, page_rows=page_rows, image_rows=image_rows)
    return page_rows, image_rows, resumed


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl citizensbank URLs and extract served image URLs")
    parser.add_argument("--urls", type=Path, default=CITIZENS_URLS_PATH)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Ignore checkpoint and start stage 01 from scratch")
    parser.set_defaults(resume=True)
    args = parser.parse_args()

    ensure_dirs()
    urls = read_url_list(args.urls)
    if not urls:
        raise SystemExit("No URLs found to crawl")

    page_rows, image_rows, resumed = crawl(urls, timeout=args.timeout, resume=args.resume)

    page_out = AUDIT_DIR / "citizens_pages.json"
    image_out = AUDIT_DIR / "citizens_images.json"
    write_json(page_out, page_rows)
    write_json(image_out, image_rows)

    image_to_pages: dict[str, set[str]] = defaultdict(set)
    for row in image_rows:
        image_to_pages[row["image_url"]].add(row["page_url"])

    write_json(
        AUDIT_DIR / "citizens_images_index.json",
        [
            {"image_url": image_url, "page_count": len(pages), "page_urls": sorted(pages)}
            for image_url, pages in sorted(image_to_pages.items())
        ],
    )

    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink(missing_ok=True)

    emit_progress(
        current=len(page_rows),
        total=len(page_rows),
        message="Citizens crawl complete",
        resumed=resumed,
        images_discovered=len(image_rows),
        images_pending=0,
    )

    print(json.dumps({
        "pages_total": len(page_rows),
        "pages_ok": sum(1 for x in page_rows if x["status"] == "ok"),
        "pages_error": sum(1 for x in page_rows if x["status"] != "ok"),
        "image_refs": len(image_rows),
        "unique_images": len(image_to_pages),
        "resumed": resumed,
        "checkpoint_path": str(CHECKPOINT_PATH),
        "images_pending": 0,
        "page_output": str(page_out),
        "image_output": str(image_out),
    }, indent=2))


if __name__ == "__main__":
    main()
