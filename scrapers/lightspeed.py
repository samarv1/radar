"""
Lightspeed Venture Partners portfolio scraper.

Extracts the company list embedded in lsvp.com/companies/ as a JS variable
(window.companiesAutocomplete), then cross-references with the sitemap to
get slugs for source URLs. Upserts into accelerator_companies.

Usage:
    uv run python scrapers/lightspeed.py
"""

import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

LISTING_URL = "https://lsvp.com/companies/"
SITEMAP_URL = "https://lsvp.com/company-sitemap.xml"
HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}
SLEEP = 0.4


def fetch_company_names() -> list[str]:
    resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    match = re.search(r"window\.companiesAutocomplete = (\[.*?\]);", resp.text, re.DOTALL)
    if not match:
        raise RuntimeError("Could not find companiesAutocomplete in page")
    return json.loads(match.group(1))


def fetch_slugs_from_sitemap() -> list[str]:
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return re.findall(r"https://lsvp\.com/company/([^/]+)/", resp.text)


def slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def upsert_company(conn, row: dict) -> bool:
    sql = """
        INSERT INTO accelerator_companies
            (name, accelerator, description, source_url)
        VALUES
            (%(name)s, 'lightspeed', %(description)s, %(source_url)s)
        ON CONFLICT (source_url) DO UPDATE SET
            name        = EXCLUDED.name,
            updated_at  = NOW()
        RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
        result = cur.fetchone()
        return result[0] if result else False


def scrape():
    print("Fetching Lightspeed company names from listing page...")
    names = fetch_company_names()
    print(f"  Found {len(names)} companies")
    time.sleep(SLEEP)

    print("Fetching slugs from sitemap...")
    slugs = fetch_slugs_from_sitemap()
    print(f"  Found {len(slugs)} slugs")

    # Build a name→slug map via normalized matching
    slug_map = {slug_to_name(s).lower(): s for s in slugs}

    conn = get_connection()
    inserted = updated = 0

    try:
        for name in names:
            slug = slug_map.get(name.lower())
            source_url = f"https://lsvp.com/company/{slug}/" if slug else f"https://lsvp.com/companies/?s={name.replace(' ', '+')}"

            row = {"name": name, "description": None, "source_url": source_url}
            is_new = upsert_company(conn, row)
            if is_new:
                inserted += 1
                print(f"  NEW  {name}")
            else:
                updated += 1

        conn.commit()
    finally:
        conn.close()

    print(f"\nDone. Inserted: {inserted}, Updated: {updated}")


if __name__ == "__main__":
    scrape()
