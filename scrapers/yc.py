"""
YC company directory scraper.

Uses the public Algolia search index backing ycombinator.com/companies.
Writes into accelerator_companies with accelerator='yc'.

Usage:
    uv run python scrapers/yc.py
"""

import sys
import time

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import apply_schema, get_connection

ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_API_KEY = "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
ALGOLIA_INDEX = "YCCompany_production"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"

HEADERS = {
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
}

SLEEP = 0.2


def fetch_all_companies() -> list[dict]:
    companies = []
    page = 0
    total_pages = None

    while True:
        payload = {
            "query": "",
            "hitsPerPage": 1000,
            "page": page,
            "attributesToRetrieve": ["name", "batch", "one_liner", "website", "tags", "slug"],
        }

        resp = requests.post(ALGOLIA_URL, json=payload, headers=HEADERS, timeout=30)
        time.sleep(SLEEP)

        if resp.status_code != 200:
            print(f"Algolia error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        hits = data.get("hits", [])
        if total_pages is None:
            total_pages = data.get("nbPages", 1)
            print(f"YC directory: {data.get('nbHits', '?')} companies across {total_pages} pages")

        companies.extend(hits)
        print(f"  Page {page + 1}/{total_pages}: {len(hits)} companies")

        page += 1
        if page >= total_pages:
            break

    return companies


def upsert_company(conn, row: dict) -> bool:
    sql = """
        INSERT INTO accelerator_companies
            (name, website, accelerator, batch, description, tags, source_url)
        VALUES
            (%(name)s, %(website)s, 'yc', %(batch)s, %(description)s, %(tags)s, %(source_url)s)
        ON CONFLICT (source_url) DO UPDATE SET
            name        = EXCLUDED.name,
            website     = EXCLUDED.website,
            batch       = EXCLUDED.batch,
            description = EXCLUDED.description,
            tags        = EXCLUDED.tags,
            updated_at  = NOW()
        RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
        result = cur.fetchone()
        return result[0] if result else False


def scrape():
    print("Applying DB schema...")
    apply_schema()

    hits = fetch_all_companies()
    print(f"Total hits: {len(hits)}")

    conn = get_connection()
    inserted = updated = skipped = 0

    try:
        for hit in hits:
            slug = hit.get("slug", "")
            if not slug or not hit.get("name", "").strip():
                skipped += 1
                continue

            tags = hit.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]

            row = {
                "name": hit["name"].strip(),
                "website": (hit.get("website") or "").strip() or None,
                "batch": (hit.get("batch") or "").strip() or None,
                "description": (hit.get("one_liner") or "").strip() or None,
                "tags": tags,
                "source_url": f"https://www.ycombinator.com/companies/{slug}",
            }

            is_new = upsert_company(conn, row)
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
