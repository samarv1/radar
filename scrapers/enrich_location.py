"""
Enrich accelerator_companies with a location_tag derived from matched EDGAR
filings, for companies whose source (a16z, pear, sequoia, lightspeed, or any
YC/Techstars row scraped before location capture was added) has no direct
city/state/country field.

For each company with location_tag IS NULL, finds its most recent matched
edgar_filings row (by accelerator_id, falling back to a case-insensitive name
match) and classifies hq_city/hq_state/hq_country from it. Companies with no
EDGAR match stay 'unknown'.

Usage:
    uv run python -m scrapers.enrich_location [--all]

By default only processes un-enriched rows (location_tag IS NULL).
Pass --all to re-process everything (useful after expanding the city lookup
tables in scrapers/location.py).
"""

import argparse

from db.connection import get_connection
from scrapers.location import classify_edgar_state_field


def find_edgar_location(cur, company_id: int, name: str) -> tuple[str | None, str | None]:
    """Returns (city, state) from the best-matching edgar_filings row, or (None, None)."""
    cur.execute(
        """
        SELECT city, state FROM edgar_filings
        WHERE accelerator_id = %s
        ORDER BY date_filed DESC NULLS LAST
        LIMIT 1
        """,
        (company_id,),
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1]

    cur.execute(
        """
        SELECT city, state FROM edgar_filings
        WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(%s))
        ORDER BY date_filed DESC NULLS LAST
        LIMIT 1
        """,
        (name,),
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1]

    return None, None


def run(reprocess_all: bool = False):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if reprocess_all:
                cur.execute("SELECT id, name FROM accelerator_companies")
            else:
                cur.execute(
                    "SELECT id, name FROM accelerator_companies WHERE location_tag IS NULL"
                )
            rows = cur.fetchall()

        print(f"Enriching {len(rows)} companies...")

        updated = 0
        for company_id, name in rows:
            with conn.cursor() as cur:
                city, state = find_edgar_location(cur, company_id, name)

            location_tag = classify_edgar_state_field(city, state)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE accelerator_companies
                    SET hq_city = %s, hq_state = %s, location_tag = %s
                    WHERE id = %s
                    """,
                    (city, state, location_tag, company_id),
                )
            updated += 1

            tag_note = f" ← {location_tag}" if location_tag != "unknown" else ""
            print(f"  OK    {name[:40]:<40}  city={city or '?'} state={state or '?'}{tag_note}")

            if updated % 50 == 0:
                conn.commit()

        conn.commit()
        print(f"\nDone. Enriched {updated}/{len(rows)} companies.")

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Re-process already-enriched companies")
    args = parser.parse_args()
    run(reprocess_all=args.all)
