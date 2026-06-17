"""
Data quality validation report for Phase 1 pipeline.

Prints a structured report to stdout covering EDGAR filings,
YC companies, and cross-reference match quality.

Usage:
    uv run python validate.py
"""

import sys
from db.connection import get_connection


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def query(conn, sql: str, params=None) -> list:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def validate_edgar(conn):
    section("EDGAR FILINGS")

    # Total
    total = query(conn, "SELECT COUNT(*) FROM edgar_filings")[0][0]
    print(f"Total filings: {total}")

    if total == 0:
        print("  (no data)")
        return

    # Date range
    row = query(conn, "SELECT MIN(date_filed), MAX(date_filed) FROM edgar_filings")[0]
    print(f"Date range: {row[0]} to {row[1]}")

    # % with amount_raised
    with_amount = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE amount_raised IS NOT NULL AND amount_raised > 0")[0][0]
    pct_amount = (with_amount / total * 100) if total else 0
    print(f"With amount_raised populated: {with_amount}/{total} ({pct_amount:.1f}%)")

    # % with industry_group
    with_ig = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE industry_group IS NOT NULL")[0][0]
    pct_ig = (with_ig / total * 100) if total else 0
    print(f"With industry_group populated: {with_ig}/{total} ({pct_ig:.1f}%)")

    # Filings by month
    print("\nFilings by month:")
    rows = query(conn, """
        SELECT TO_CHAR(date_filed, 'YYYY-MM') AS month, COUNT(*) AS cnt
        FROM edgar_filings
        WHERE date_filed IS NOT NULL
        GROUP BY month
        ORDER BY month
    """)
    for month, cnt in rows:
        bar = "#" * min(cnt // 5, 60)
        print(f"  {month}: {cnt:4d}  {bar}")

    # Duplicate detection (same company name + date, different accession)
    duplicates = query(conn, """
        SELECT company_name, date_filed, COUNT(*) AS cnt
        FROM edgar_filings
        WHERE date_filed IS NOT NULL
        GROUP BY company_name, date_filed
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 10
    """)
    if duplicates:
        print(f"\nPotential duplicate filings (same name+date, different accession): {len(duplicates)}")
        for name, d, cnt in duplicates:
            print(f"  [{cnt}x] {name} on {d}")
    else:
        print("\nNo duplicate name+date combinations found.")

    # Anomaly: amount_raised = 0
    zero_amount = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE amount_raised = 0")[0][0]
    if zero_amount:
        print(f"\nANOMALY: {zero_amount} filings with amount_raised=0 (likely undisclosed — confirm expected)")

    # Anomaly: date_of_first_sale in the future
    future_dates = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE date_of_first_sale > CURRENT_DATE")[0][0]
    if future_dates:
        print(f"ANOMALY: {future_dates} filings with date_of_first_sale in the future (possible data error)")

    # 10 random sample rows
    print("\n10 random sample EDGAR filings:")
    samples = query(conn, """
        SELECT company_name, state, date_filed, amount_raised, industry_group, entity_type, accession_number
        FROM edgar_filings
        ORDER BY RANDOM()
        LIMIT 10
    """)
    print(f"  {'Company':<40} {'State':<6} {'Filed':<12} {'Amount':>12} {'Industry':<30} {'Type':<20}")
    print(f"  {'-'*40} {'-'*6} {'-'*12} {'-'*12} {'-'*30} {'-'*20}")
    for name, state, filed, amount, ig, etype, accession in samples:
        amount_str = f"${amount:,.0f}" if amount else "N/A"
        print(f"  {(name or '')[:40]:<40} {(state or '')[:6]:<6} {str(filed or ''):<12} {amount_str:>12} {(ig or '')[:30]:<30} {(etype or '')[:20]:<20}")


def validate_yc(conn):
    section("YC COMPANIES")

    total = query(conn, "SELECT COUNT(*) FROM yc_companies")[0][0]
    print(f"Total companies: {total}")

    if total == 0:
        print("  (no data)")
        return

    # Batch distribution
    print("\nBatch distribution:")
    rows = query(conn, """
        SELECT batch, COUNT(*) AS cnt
        FROM yc_companies
        WHERE batch IS NOT NULL AND batch != ''
        GROUP BY batch
        ORDER BY batch DESC
        LIMIT 20
    """)
    for batch, cnt in rows:
        print(f"  {batch:<8} {cnt:4d}")

    # % with website
    with_website = query(conn, "SELECT COUNT(*) FROM yc_companies WHERE website IS NOT NULL AND website != ''")[0][0]
    pct_web = (with_website / total * 100) if total else 0
    print(f"\nWith website: {with_website}/{total} ({pct_web:.1f}%)")

    # Anomaly: no website
    no_website = total - with_website
    if no_website:
        print(f"ANOMALY: {no_website} companies with no website")

    # 10 random samples
    print("\n10 random sample YC companies:")
    samples = query(conn, """
        SELECT name, batch, description, website
        FROM yc_companies
        ORDER BY RANDOM()
        LIMIT 10
    """)
    print(f"  {'Name':<35} {'Batch':<8} {'Description':<50} {'Website':<30}")
    print(f"  {'-'*35} {'-'*8} {'-'*50} {'-'*30}")
    for name, batch, desc, website in samples:
        print(f"  {(name or '')[:35]:<35} {(batch or ''):<8} {(desc or '')[:50]:<50} {(website or '')[:30]:<30}")


def validate_cross_reference(conn):
    section("CROSS-REFERENCE MATCHES")

    total = query(conn, "SELECT COUNT(*) FROM matches")[0][0]
    print(f"Total matches: {total}")

    if total == 0:
        print("  (no data — run scrapers/cross_reference.py first)")
        return

    # Score distribution
    print("\nScore distribution:")
    buckets = [(85, 89), (90, 94), (95, 100)]
    for lo, hi in buckets:
        cnt = query(conn, "SELECT COUNT(*) FROM matches WHERE match_score >= %s AND match_score <= %s", (lo, hi))[0][0]
        print(f"  {lo}-{hi}: {cnt}")

    # All matches with score >= 85
    print("\nAll matches (score >= 85):")
    matches = query(conn, """
        SELECT m.match_score, e.company_name, y.name, y.batch, y.website
        FROM matches m
        JOIN edgar_filings e ON m.edgar_id = e.id
        JOIN yc_companies y ON m.yc_id = y.id
        WHERE m.match_score >= 85
        ORDER BY m.match_score DESC
    """)

    print(f"  {'Score':>6}  {'EDGAR Name':<40} {'YC Name':<40} {'Batch':<8} {'Website':<30}")
    print(f"  {'-'*6}  {'-'*40} {'-'*40} {'-'*8} {'-'*30}")
    for score, edgar_name, yc_name, batch, website in matches:
        flag = " [REVIEW]" if score <= 92 else ""
        print(f"  {score:>6.0f}  {(edgar_name or '')[:40]:<40} {(yc_name or '')[:40]:<40} {(batch or ''):<8} {(website or '')[:30]:<30}{flag}")

    # Summary of acceptance criteria
    section("ACCEPTANCE CRITERIA CHECK")

    edgar_total = query(conn, "SELECT COUNT(*) FROM edgar_filings")[0][0]
    yc_total = query(conn, "SELECT COUNT(*) FROM yc_companies")[0][0]
    match_total = total

    # Unique batches
    batch_rows = query(conn, """
        SELECT COUNT(DISTINCT batch) FROM yc_companies
        WHERE batch IS NOT NULL AND batch != ''
    """)
    unique_batches = batch_rows[0][0]

    # Amount raised pct
    if edgar_total > 0:
        with_amount = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE amount_raised IS NOT NULL AND amount_raised > 0")[0][0]
        pct_amount = with_amount / edgar_total * 100
    else:
        pct_amount = 0

    high_conf = query(conn, "SELECT COUNT(*) FROM matches WHERE match_score >= 93")[0][0]

    checks = [
        ("EDGAR >= 200 filings for last 90 days", edgar_total >= 200, f"{edgar_total} filings"),
        (">=60% filings have amount_raised", pct_amount >= 60, f"{pct_amount:.1f}%"),
        ("YC has companies from >= 4 batches", unique_batches >= 4, f"{unique_batches} unique batches"),
        (">=5 plausible YC+EDGAR matches", match_total >= 5, f"{match_total} matches"),
        (">=1 high-confidence match (score>=93) for manual review", high_conf >= 1, f"{high_conf} high-conf matches"),
    ]

    all_pass = True
    for label, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label} — {detail}")

    if all_pass:
        print("\nAll acceptance criteria met. Ready for Phase 2.")
    else:
        print("\nSome criteria not yet met. Review above before proceeding to Phase 2.")


def main():
    conn = get_connection()
    try:
        validate_edgar(conn)
        validate_yc(conn)
        validate_cross_reference(conn)
    finally:
        conn.close()

    print("\n")


if __name__ == "__main__":
    main()
