"""
Sequoia Capital portfolio scraper.

Paginates the public company listing at sequoiacap.com/our-companies
using the FacetWP ?fwp_paged=N parameter. Filters to early-stage companies
partnered in 2018 or later (the Series A–C sweet spot).

Writes into accelerator_companies with accelerator='sequoia'.

Usage:
    uv run python -m scrapers.sequoia [--all-stages] [--min-year 2018]
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from scrapers._common import DEFAULT_HEADERS, execute_upsert, run_upsert_batch

BASE_URL = "https://www.sequoiacap.com/our-companies/"
WP_API = "https://sequoiacap.com/wp-json/wp/v2/company"
HEADERS = DEFAULT_HEADERS
SLEEP = 0.4

# Stages we care about — exclude large exits and very old investments
INCLUDED_STAGES = {"pre-seed/seed", "early"}


def parse_html_table() -> dict[str, dict]:
    """
    Parse the server-rendered HTML table (all companies are in page 1).
    Returns a dict keyed by company name with stage + year.
    """
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        print(f"  HTML fetch error: {resp.status_code}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("tr[data-target]")
    result = {}

    for row in rows:
        cells = row.find_all(["th", "td"])
        if len(cells) < 6:
            continue

        name = cells[1].get_text(strip=True)
        desc = cells[2].get_text(strip=True)
        year_text = cells[5].get_text(strip=True)  # e.g. "Pre-Seed/Seed (2021)"

        year_match = re.search(r"\((\d{4})\)", year_text)
        year = int(year_match.group(1)) if year_match else None
        stage = re.sub(r"\s*\(\d{4}\)\s*$", "", year_text).strip()

        if name:
            result[name] = {"desc": desc, "stage": stage, "year": year}

    return result


def fetch_all_companies_wp() -> list[dict]:
    """Fetch all company slugs + names via WP REST API."""
    companies = []
    page = 1
    while True:
        resp = requests.get(
            WP_API,
            params={"per_page": 100, "page": page, "_fields": "id,title,slug"},
            headers=HEADERS,
            timeout=20,
        )
        if resp.status_code == 400:
            break
        if resp.status_code != 200:
            print(f"WP API error {resp.status_code}")
            break
        hits = resp.json()
        if not hits:
            break
        if page == 1:
            total = resp.headers.get("X-WP-Total", "?")
            print(f"Sequoia WP API: {total} companies")
        companies.extend(hits)
        time.sleep(SLEEP)
        page += 1
    return companies


def upsert_company(conn, row: dict) -> bool:
    sql = """
        INSERT INTO accelerator_companies
            (name, accelerator, batch, description, stage, source_url)
        VALUES
            (%(name)s, 'sequoia', %(batch)s, %(description)s, %(stage)s, %(source_url)s)
        ON CONFLICT (source_url) DO UPDATE SET
            name        = EXCLUDED.name,
            batch       = EXCLUDED.batch,
            description = EXCLUDED.description,
            stage       = EXCLUDED.stage,
            updated_at  = NOW()
        RETURNING (xmax = 0) AS inserted
    """
    return execute_upsert(conn, sql, row)


def scrape(min_year: int = 2018, all_stages: bool = False, conn=None):
    print("Fetching Sequoia HTML table (stage + year data)...")
    table_data = parse_html_table()
    print(f"  Found {len(table_data)} companies with stage/year data")
    time.sleep(SLEEP)

    wp_companies = fetch_all_companies_wp()
    print(f"  WP API returned {len(wp_companies)} companies")

    # Merge: WP API is the canonical list; HTML table provides stage/year enrichment
    merged = []
    for hit in wp_companies:
        name = (hit.get("title") or {}).get("rendered", "").strip()
        slug = hit.get("slug", "")
        if not name or not slug:
            continue

        meta = table_data.get(name, {})
        year = meta.get("year")
        stage = meta.get("stage", "")
        desc = meta.get("desc", "")

        merged.append({
            "name": name,
            "slug": slug,
            "year": year,
            "stage": stage,
            "desc": desc,
        })

    print(f"\nTotal merged: {len(merged)}")

    # Filter: include all companies; if year data available, optionally restrict.
    # Stage filtering is NOT applied here — EDGAR filing date/amount serves as
    # the real "recently raised" indicator.
    filtered = []
    for c in merged:
        if not all_stages and c["year"] and c["year"] < min_year:
            continue
        filtered.append(c)

    print(f"After filtering (year>={min_year} where known, all_stages={all_stages}): {len(filtered)}")

    rows = []
    for c in filtered:
        slug = c["slug"]
        rows.append({
            "name": c["name"],
            "batch": str(c["year"]) if c["year"] else None,
            "description": c["desc"] or None,
            "stage": c["stage"] or None,
            "source_url": f"https://sequoiacap.com/companies/{slug}/",
        })

    inserted, updated = run_upsert_batch(rows, upsert_company, conn=conn)
    print(f"Done. Inserted: {inserted}, Updated: {updated}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--min-year", type=int, default=2018)
    parser.add_argument("--all-stages", action="store_true")
    args = parser.parse_args()

    scrape(min_year=args.min_year, all_stages=args.all_stages)
