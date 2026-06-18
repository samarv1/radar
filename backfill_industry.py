"""
Backfill industry_group and date_of_first_sale for existing EDGAR filings
by re-fetching each raw_url and re-parsing the XML.

Also deletes records whose industry_group turns out to be excluded
(Real Estate, Pooled Investment Fund).

Usage:
    uv run python backfill_industry.py
"""

import sys
import time

import requests

sys.path.insert(0, ".")
from db.connection import get_connection
from scrapers.edgar import parse_form_d_xml, is_excluded_by_xml, HEADERS, SLEEP

SLEEP = 0.15


def backfill():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, raw_url, company_name FROM edgar_filings ORDER BY id")
    rows = cur.fetchall()
    print(f"Backfilling {len(rows)} filings...")

    updated = 0
    deleted = 0
    failed = 0

    for i, (filing_id, raw_url, company_name) in enumerate(rows):
        print(f"[{i+1}/{len(rows)}] {company_name}", end="")

        if not raw_url:
            print(" — no URL, skipping")
            failed += 1
            continue

        try:
            resp = requests.get(raw_url, headers=HEADERS, timeout=20)
            time.sleep(SLEEP)
            if resp.status_code != 200 or "<" not in resp.text:
                print(f" — HTTP {resp.status_code}, skipping")
                failed += 1
                continue
        except Exception as e:
            print(f" — request error: {e}")
            failed += 1
            continue

        parsed = parse_form_d_xml(resp.text)

        if is_excluded_by_xml(parsed):
            cur.execute("DELETE FROM edgar_filings WHERE id = %s", (filing_id,))
            conn.commit()
            deleted += 1
            print(f" — DELETED (excluded: {parsed.get('industry_group')})")
            continue

        cur.execute(
            """
            UPDATE edgar_filings SET
                industry_group = %s,
                date_of_first_sale = %s,
                amount_raised = CASE WHEN %s IS NOT NULL THEN %s ELSE amount_raised END
            WHERE id = %s
            """,
            (
                parsed.get("industry_group"),
                parsed.get("date_of_first_sale"),
                parsed.get("amount_raised"),
                parsed.get("amount_raised"),
                filing_id,
            ),
        )
        conn.commit()
        updated += 1
        ig = parsed.get("industry_group") or "(none)"
        print(f" — updated (industry: {ig})")

    conn.close()
    print(f"\nDone. Updated: {updated}, Deleted (excluded): {deleted}, Failed: {failed}")


if __name__ == "__main__":
    backfill()
