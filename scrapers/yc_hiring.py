"""
YC hiring signal scraper.

Fetches YC companies marked isHiring=true from the public Algolia index,
matches them to accelerator_companies, and resets careers_scraped_at so
the next careers sweep picks them up immediately.

Usage:
    uv run python scrapers/yc_hiring.py
"""

import sys
import time

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_API_KEY = "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/YCCompany_production/query"
HEADERS = {
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
}
SLEEP = 0.2


def fetch_hiring_companies() -> list[dict]:
    companies = []
    page = 0
    while True:
        payload = {
            "query": "",
            "hitsPerPage": 1000,
            "page": page,
            "filters": "isHiring:true",
            "attributesToRetrieve": ["name", "slug", "website", "batch"],
        }
        resp = requests.post(ALGOLIA_URL, json=payload, headers=HEADERS, timeout=30)
        time.sleep(SLEEP)
        if resp.status_code != 200:
            raise RuntimeError(f"Algolia request failed: {resp.status_code}")
        data = resp.json()
        hits = data.get("hits", [])
        companies.extend(hits)
        if page >= data.get("nbPages", 1) - 1:
            break
        page += 1
    return companies


def scrape():
    print("Fetching YC companies marked as hiring...")
    companies = fetch_hiring_companies()
    print(f"Found {len(companies)} YC companies with isHiring=true")

    conn = get_connection()
    try:
        matched_ids = set()

        with conn.cursor() as cur:
            for c in companies:
                name = c.get("name", "").strip()
                slug = c.get("slug", "").strip()
                website = c.get("website", "").strip()

                # Match by slug first (most reliable), then name
                cur.execute(
                    """
                    SELECT id FROM accelerator_companies
                    WHERE accelerator = 'yc'
                      AND is_excluded = FALSE
                      AND (
                        LOWER(TRIM(name)) = LOWER(%s)
                        OR (website IS NOT NULL AND LOWER(website) = LOWER(%s))
                      )
                    LIMIT 1
                    """,
                    (name, website),
                )
                row = cur.fetchone()
                if row:
                    matched_ids.add(row[0])

        reset_count = 0
        if matched_ids:
            with conn.cursor() as cur:
                # Only reset companies not scraped in last 7 days — avoids re-scraping
                # the entire hiring cohort every day.
                cur.execute(
                    """
                    UPDATE accelerator_companies
                    SET careers_scraped_at = NULL
                    WHERE id = ANY(%s)
                      AND (careers_scraped_at IS NULL
                           OR careers_scraped_at < NOW() - INTERVAL '7 days')
                    """,
                    (list(matched_ids),),
                )
                reset_count = cur.rowcount
            conn.commit()

        print(f"Matched {len(matched_ids)} companies in DB → reset {reset_count} careers_scraped_at (stale >7d)")
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    scrape()
