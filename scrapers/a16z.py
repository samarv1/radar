"""
Andreessen Horowitz (a16z) portfolio scraper.

Fetches the portfolio page which embeds all 800+ companies as a JSON array
in a data-companies HTML attribute. Filters to active (non-exit) companies.
Writes into accelerator_companies with accelerator='a16z'.

Usage:
    uv run python scrapers/a16z.py
"""

import html as html_lib
import re
import sys
import time

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

PORTFOLIO_URL = "https://a16z.com/portfolio/"
HEADERS = {"User-Agent": "radar-tool contact@example.com"}
SLEEP = 1.0

# Stages to exclude — these are exits, not potential employers
EXCLUDED_STATUSES = {"Exits"}
EXCLUDED_STAGES = {"IPO", "M&A"}


def fetch_companies() -> list[dict]:
    resp = requests.get(PORTFOLIO_URL, headers=HEADERS, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"a16z portfolio fetch failed: {resp.status_code}")
    time.sleep(SLEEP)

    m = re.search(r'data-companies="([^"]{1000,})"', resp.text)
    if not m:
        raise RuntimeError("data-companies attribute not found in a16z portfolio HTML")

    decoded = html_lib.unescape(m.group(1))
    return json_parse(decoded)


def json_parse(s: str) -> list[dict]:
    import json
    return json.loads(s)


def is_target(company: dict) -> bool:
    if company.get("status") in EXCLUDED_STATUSES:
        return False
    stages = company.get("stages") or []
    if isinstance(stages, list) and any(s in EXCLUDED_STAGES for s in stages):
        return False
    return True


def upsert_company(conn, row: dict) -> bool:
    sql = """
        INSERT INTO accelerator_companies
            (name, website, accelerator, batch, description, tags, stage, source_url)
        VALUES
            (%(name)s, %(website)s, 'a16z', %(batch)s, %(description)s, %(tags)s, %(stage)s, %(source_url)s)
        ON CONFLICT (source_url) DO UPDATE SET
            name        = EXCLUDED.name,
            website     = EXCLUDED.website,
            batch       = EXCLUDED.batch,
            description = EXCLUDED.description,
            tags        = EXCLUDED.tags,
            stage       = EXCLUDED.stage,
            updated_at  = NOW()
        RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
        result = cur.fetchone()
        return result[0] if result else False


def scrape():
    print("Fetching a16z portfolio page...")
    companies = fetch_companies()
    print(f"Found {len(companies)} total companies")

    targets = [c for c in companies if is_target(c)]
    print(f"After filtering exits: {len(targets)} companies")

    conn = get_connection()
    inserted = updated = skipped = 0

    try:
        for c in targets:
            name = c.get("name", "").strip()
            if not name:
                skipped += 1
                continue

            permalink = (c.get("permalink") or "").strip()
            if not permalink:
                skipped += 1
                continue

            stages = c.get("stages") or []
            stage = ", ".join(stages) if isinstance(stages, list) else str(stages or "")

            focus_areas = c.get("focus_areas") or []
            tags = [f for f in focus_areas if isinstance(f, str)] if isinstance(focus_areas, list) else []

            year_founded = (c.get("year_founded") or "").strip() or None

            row = {
                "name": name,
                "website": (c.get("company_url") or "").strip() or None,
                "batch": year_founded,
                "description": (c.get("website_description") or "").strip() or None,
                "tags": tags or None,
                "stage": stage or None,
                "source_url": permalink,
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
