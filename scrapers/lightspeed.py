"""
Lightspeed Venture Partners portfolio scraper.

Extracts the company list embedded in lsvp.com/companies/ as a JS variable
(window.companiesAutocomplete), then cross-references with the sitemap to
get slugs for source URLs. Upserts into accelerator_companies.

Usage:
    uv run python -m scrapers.lightspeed
"""

import json
import re
import time

import requests

from scrapers._common import DEFAULT_HEADERS, execute_upsert, run_upsert_batch

LISTING_URL = "https://lsvp.com/companies/"
SITEMAP_URL = "https://lsvp.com/company-sitemap.xml"
HEADERS = DEFAULT_HEADERS
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
    is_new = execute_upsert(conn, sql, row)
    if is_new:
        print(f"  NEW  {row['name']}")
    return is_new


def scrape(conn=None):
    print("Fetching Lightspeed company names from listing page...")
    names = fetch_company_names()
    print(f"  Found {len(names)} companies")
    time.sleep(SLEEP)

    print("Fetching slugs from sitemap...")
    slugs = fetch_slugs_from_sitemap()
    print(f"  Found {len(slugs)} slugs")

    slug_map = {slug_to_name(s).lower(): s for s in slugs}

    rows = []
    for name in names:
        slug = slug_map.get(name.lower())
        source_url = f"https://lsvp.com/company/{slug}/" if slug else f"https://lsvp.com/companies/?s={name.replace(' ', '+')}"
        rows.append({"name": name, "description": None, "source_url": source_url})

    inserted, updated = run_upsert_batch(rows, upsert_company, conn=conn)
    print(f"\nDone. Inserted: {inserted}, Updated: {updated}")


if __name__ == "__main__":
    scrape()
