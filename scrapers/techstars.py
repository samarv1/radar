"""
Techstars portfolio scraper.

Queries the Typesense search API embedded in techstars.com/portfolio to pull
all accelerator companies (not just network members). Filters to US companies
from 2018 onwards. Upserts into accelerator_companies.

Usage:
    uv run python -m scrapers.techstars [--all-countries] [--min-year 2018]
"""

import time

import requests

from db.connection import apply_schema
from scrapers._common import execute_upsert, run_upsert_batch
from scrapers.location import classify_location

TYPESENSE_URL = "https://8gbms7c94riane0lp-1.a1.typesense.net"
TYPESENSE_KEY = "0QKFSu4mIDX9UalfCNQN4qjg2xmukDE0"
HEADERS = {"X-Typesense-Api-Key": TYPESENSE_KEY}
PER_PAGE = 250
SLEEP = 0.2


def fetch_page(page: int, filter_by: str) -> dict:
    params = {
        "q": "*",
        "per_page": PER_PAGE,
        "page": page,
        "filter_by": filter_by,
        "sort_by": "first_session_year:desc",
    }
    resp = requests.get(
        f"{TYPESENSE_URL}/collections/companies/documents/search",
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_all(filter_by: str) -> list[dict]:
    first = fetch_page(1, filter_by)
    total = first["found"]
    pages = (total + PER_PAGE - 1) // PER_PAGE
    print(f"  Found {total} companies across {pages} pages")

    results = [hit["document"] for hit in first["hits"]]

    for page in range(2, pages + 1):
        time.sleep(SLEEP)
        data = fetch_page(page, filter_by)
        results.extend(hit["document"] for hit in data["hits"])
        print(f"  Page {page}/{pages} — {len(results)} fetched", end="\r")

    print()
    return results


def upsert_company(conn, row: dict) -> bool:
    sql = """
        INSERT INTO accelerator_companies
            (name, website, accelerator, batch, description, tags, source_url,
             hq_city, hq_state, hq_country, location_tag)
        VALUES
            (%(name)s, %(website)s, 'techstars', %(batch)s, %(description)s, %(tags)s, %(source_url)s,
             %(hq_city)s, %(hq_state)s, %(hq_country)s, %(location_tag)s)
        ON CONFLICT (source_url) DO UPDATE SET
            name        = EXCLUDED.name,
            website     = EXCLUDED.website,
            batch       = EXCLUDED.batch,
            tags        = EXCLUDED.tags,
            hq_city     = EXCLUDED.hq_city,
            hq_state    = EXCLUDED.hq_state,
            hq_country  = EXCLUDED.hq_country,
            location_tag = EXCLUDED.location_tag,
            updated_at  = NOW()
        RETURNING (xmax = 0) AS inserted
    """
    return execute_upsert(conn, sql, row)


def scrape(min_year: int = 2018, all_countries: bool = False, conn=None):
    print("Applying DB schema...")
    apply_schema()

    filter_parts = ["is_accelerator_company:true"]
    if not all_countries:
        filter_parts.append("country:United States")
    filter_by = " && ".join(filter_parts)

    print(f"Fetching Techstars companies (filter: {filter_by})...")
    companies = fetch_all(filter_by)

    # Apply year filter client-side (Typesense numeric filter syntax is finicky)
    before_filter = len(companies)
    companies = [c for c in companies if not c.get("first_session_year") or c["first_session_year"] >= min_year]
    print(f"After year filter (>={min_year}): {len(companies)} of {before_filter}")

    rows = []
    for c in companies:
        name = c.get("company_name", "").strip()
        if not name:
            continue

        company_id = c.get("company_id", "")
        website = c.get("website", "") or None
        year = c.get("first_session_year")
        tags = c.get("industry_vertical", []) or []
        programs = c.get("program_names", [])
        batch = str(year) if year else None

        hq_city = c.get("city") or None
        hq_state = c.get("state_province") or None
        hq_country = c.get("country") or None
        location_tag = classify_location(hq_city, hq_state, hq_country)

        rows.append({
            "name": name,
            "website": f"https://{website}" if website and not website.startswith("http") else website,
            "batch": batch,
            "description": programs[0] if programs else None,
            "tags": tags or None,
            "source_url": f"https://www.techstars.com/portfolio#{company_id}",
            "hq_city": hq_city,
            "hq_state": hq_state,
            "hq_country": hq_country,
            "location_tag": location_tag,
        })

    inserted, updated = run_upsert_batch(rows, upsert_company, conn=conn)
    print(f"Done. Inserted: {inserted}, Updated: {updated}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--min-year", type=int, default=2018)
    parser.add_argument("--all-countries", action="store_true")
    args = parser.parse_args()

    scrape(min_year=args.min_year, all_countries=args.all_countries)
