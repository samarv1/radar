"""
Pear VC portfolio scraper.

Uses Pear's WordPress REST API (pear_vc_company post type).
Writes into accelerator_companies with accelerator='pear'.

Usage:
    uv run python -m scrapers.pear
"""

import time

import requests

from scrapers._common import DEFAULT_HEADERS, execute_upsert, run_upsert_batch

BASE = "https://pear.vc/wp-json/wp/v2/pear_vc_company"
HEADERS = DEFAULT_HEADERS
PER_PAGE = 100
SLEEP = 0.3


def fetch_all_companies() -> list[dict]:
    companies = []
    page = 1

    while True:
        resp = requests.get(
            BASE,
            params={
                "per_page": PER_PAGE,
                "page": page,
                "_fields": "id,title,link,slug,meta",
            },
            headers=HEADERS,
            timeout=30,
        )

        if resp.status_code == 400:
            break
        if resp.status_code != 200:
            print(f"Pear API error {resp.status_code} on page {page}")
            break

        hits = resp.json()
        if not hits:
            break

        if page == 1:
            total = int(resp.headers.get("X-WP-Total", 0))
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            print(f"Pear VC directory: {total} companies across {total_pages} pages")

        companies.extend(hits)
        print(f"  Page {page}: {len(hits)} companies")
        time.sleep(SLEEP)
        page += 1

    return companies


def upsert_company(conn, row: dict) -> bool:
    sql = """
        INSERT INTO accelerator_companies
            (name, website, accelerator, description, jobs_url, source_url)
        VALUES
            (%(name)s, %(website)s, 'pear', %(description)s, %(jobs_url)s, %(source_url)s)
        ON CONFLICT (source_url) DO UPDATE SET
            name        = EXCLUDED.name,
            website     = EXCLUDED.website,
            description = EXCLUDED.description,
            jobs_url    = EXCLUDED.jobs_url,
            updated_at  = NOW()
        RETURNING (xmax = 0) AS inserted
    """
    return execute_upsert(conn, sql, row)


def scrape(conn=None):
    hits = fetch_all_companies()
    print(f"Total hits: {len(hits)}")

    rows = []
    skipped = 0

    for hit in hits:
        name = (hit.get("title") or {}).get("rendered", "").strip()
        if not name:
            skipped += 1
            continue

        meta = hit.get("meta") or {}
        if meta.get("acquired"):
            skipped += 1
            continue

        website = (
            meta.get("website_url")
            or meta.get("_links_to")
            or hit.get("link")
            or ""
        ).strip() or None

        # Skip if website is pear.vc itself (means no external link was set)
        if website and "pear.vc" in website:
            website = None

        slug = hit.get("slug", "")
        source_url = f"https://pear.vc/companies/{slug}" if slug else None
        if not source_url:
            skipped += 1
            continue

        jobs_url = (meta.get("jobs_url") or "").strip() or None
        description = (meta.get("short_description") or "").strip() or None

        rows.append({
            "name": name,
            "website": website,
            "description": description,
            "jobs_url": jobs_url,
            "source_url": source_url,
        })

    inserted, updated = run_upsert_batch(rows, upsert_company, conn=conn)
    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    scrape()
