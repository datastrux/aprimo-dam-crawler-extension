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


def crawl(urls: list[str], timeout: int) -> tuple[list[dict], list[dict]]:
    page_rows: list[dict] = []
    image_rows: list[dict] = []

    for idx, url in enumerate(urls, start=1):
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
                    image_rows.append(
                        {
                            "page_url": url,
                            "resolved_page_url": final_url,
                            "image_url": image_url,
                        }
                    )
        except Exception as err:
            row["status"] = "error"
            row["error"] = str(err)

        page_rows.append(row)
        if idx % 50 == 0:
            print(f"Crawled {idx}/{len(urls)} pages...")

    return page_rows, image_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl citizensbank URLs and extract served image URLs")
    parser.add_argument("--urls", type=Path, default=CITIZENS_URLS_PATH)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    ensure_dirs()
    urls = read_url_list(args.urls)
    if not urls:
        raise SystemExit("No URLs found to crawl")

    page_rows, image_rows = crawl(urls, timeout=args.timeout)

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

    print(json.dumps({
        "pages_total": len(page_rows),
        "pages_ok": sum(1 for x in page_rows if x["status"] == "ok"),
        "pages_error": sum(1 for x in page_rows if x["status"] != "ok"),
        "image_refs": len(image_rows),
        "unique_images": len(image_to_pages),
        "page_output": str(page_out),
        "image_output": str(image_out),
    }, indent=2))


if __name__ == "__main__":
    main()
