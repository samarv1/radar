"""
YC company directory scraper.

YC's company directory is backed by an Algolia search index. We hit the
Algolia API directly (no JS rendering needed) to paginate through all companies.

If the Algolia approach fails, install playwright and use the headless fallback:
    uv add playwright && uv run playwright install chromium

Usage:
    uv run python scrapers/yc.py
"""

import sys
import time

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import apply_schema, get_connection

# These are the public/anonymous Algolia credentials used by ycombinator.com.
# They are read-only discovery keys (not secret) discoverable from browser devtools.
ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_API_KEY = "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
ALGOLIA_INDEX = "YCCompany_production"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"

HEADERS = {
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
}

SLEEP_BETWEEN_REQUESTS = 0.2


def fetch_all_companies_algolia() -> list[dict]:
    """Paginate through all YC companies via Algolia."""
    companies = []
    page = 0
    hits_per_page = 1000
    total_pages = None

    while True:
        payload = {
            "query": "",
            "hitsPerPage": hits_per_page,
            "page": page,
            "attributesToRetrieve": [
                "name",
                "batch",
                "one_liner",
                "website",
                "tags",
                "slug",
            ],
            "filters": "",
        }

        resp = requests.post(ALGOLIA_URL, json=payload, headers=HEADERS, timeout=30)
        time.sleep(SLEEP_BETWEEN_REQUESTS)

        if resp.status_code != 200:
            print(f"Algolia request failed: {resp.status_code} {resp.text[:200]}")
            break

        data = resp.json()
        hits = data.get("hits", [])
        if total_pages is None:
            total_pages = data.get("nbPages", 1)
            print(f"Total companies: {data.get('nbHits', '?')} across {total_pages} pages")

        companies.extend(hits)
        print(f"  Page {page+1}/{total_pages}: {len(hits)} companies")

        page += 1
        if page >= total_pages:
            break

    return companies


def normalize_company(hit: dict) -> dict:
    slug = hit.get("slug", "")
    yc_url = f"https://www.ycombinator.com/companies/{slug}" if slug else ""

    tags = hit.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    return {
        "name": (hit.get("name") or "").strip(),
        "batch": (hit.get("batch") or "").strip(),
        "description": (hit.get("one_liner") or "").strip(),
        "website": (hit.get("website") or "").strip(),
        "tags": tags,
        "yc_url": yc_url,
    }


def upsert_company(conn, company: dict) -> bool:
    """Insert or update company. Returns True if inserted (new record)."""
    sql = """
        INSERT INTO yc_companies (name, batch, description, website, tags, yc_url)
        VALUES (%(name)s, %(batch)s, %(description)s, %(website)s, %(tags)s, %(yc_url)s)
        ON CONFLICT (yc_url) DO UPDATE SET
            name = EXCLUDED.name,
            batch = EXCLUDED.batch,
            description = EXCLUDED.description,
            website = EXCLUDED.website,
            tags = EXCLUDED.tags
        RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        cur.execute(sql, company)
        row = cur.fetchone()
        return row[0] if row else False


def scrape():
    print("Applying DB schema...")
    apply_schema()

    print("Fetching YC companies from Algolia...")
    hits = fetch_all_companies_algolia()
    print(f"Total hits fetched: {len(hits)}")

    conn = get_connection()
    inserted = 0
    updated = 0
    skipped = 0

    try:
        for i, hit in enumerate(hits):
            company = normalize_company(hit)

            if not company["name"] or not company["yc_url"]:
                skipped += 1
                continue

            is_new = upsert_company(conn, company)
            if is_new:
                inserted += 1
            else:
                updated += 1

        conn.commit()
    finally:
        conn.close()

    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    scrape()
