"""
Data quality validation report for Phase 1 pipeline.

Prints a structured report covering accelerator companies, EDGAR filings,
and cross-reference match quality.

Manual report, run by hand — not to be confused with scrapers/validate_standalone.py,
which is a pipeline step that tags unmatched EDGAR filings.

Usage:
    uv run python validate.py
"""

from db.connection import get_connection


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def query(conn, sql: str, params=None) -> list:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def validate_accelerator_companies(conn):
    section("ACCELERATOR COMPANIES")

    total = query(conn, "SELECT COUNT(*) FROM accelerator_companies")[0][0]
    print(f"Total companies: {total}")

    if total == 0:
        print("  (no data — run scrapers first)")
        return

    print("\nBy accelerator:")
    rows = query(conn, """
        SELECT accelerator, COUNT(*) AS cnt
        FROM accelerator_companies
        GROUP BY accelerator ORDER BY cnt DESC
    """)
    for acc, cnt in rows:
        print(f"  {acc:<12} {cnt:4d}")

    with_cik = query(conn, "SELECT COUNT(*) FROM accelerator_companies WHERE edgar_cik IS NOT NULL")[0][0]
    exact = query(conn, "SELECT COUNT(*) FROM accelerator_companies WHERE cik_confidence = 'exact'")[0][0]
    fuzzy = query(conn, "SELECT COUNT(*) FROM accelerator_companies WHERE cik_confidence = 'fuzzy'")[0][0]
    print(f"\nCIK lookup coverage: {with_cik}/{total} ({with_cik/total*100:.1f}%)")
    print(f"  Exact matches:  {exact}")
    print(f"  Fuzzy matches:  {fuzzy} [review recommended]")
    print(f"  Not yet found:  {total - with_cik}")

    print("\nYC batch distribution (top 10):")
    rows = query(conn, """
        SELECT batch, COUNT(*) AS cnt
        FROM accelerator_companies
        WHERE accelerator = 'yc' AND batch IS NOT NULL AND batch != ''
        GROUP BY batch ORDER BY batch DESC
        LIMIT 10
    """)
    for batch, cnt in rows:
        print(f"  {batch:<14} {cnt:4d}")


def validate_edgar(conn):
    section("EDGAR FILINGS")

    total = query(conn, "SELECT COUNT(*) FROM edgar_filings")[0][0]
    print(f"Total filings: {total}")

    if total == 0:
        print("  (no data)")
        return

    row = query(conn, "SELECT MIN(date_filed), MAX(date_filed) FROM edgar_filings")[0]
    print(f"Date range: {row[0]} to {row[1]}")

    with_amount = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE amount_raised IS NOT NULL AND amount_raised > 0")[0][0]
    pct_amount = (with_amount / total * 100) if total else 0
    print(f"With amount_raised populated: {with_amount}/{total} ({pct_amount:.1f}%)")

    matched = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE accelerator_id IS NOT NULL")[0][0]
    print(f"Matched to accelerator company: {matched}/{total} ({matched/total*100:.1f}%)")

    print("\nFilings by month:")
    rows = query(conn, """
        SELECT TO_CHAR(date_filed, 'YYYY-MM') AS month, COUNT(*) AS cnt
        FROM edgar_filings WHERE date_filed IS NOT NULL
        GROUP BY month ORDER BY month
    """)
    for month, cnt in rows:
        bar = "#" * min(cnt // 5, 60)
        print(f"  {month}: {cnt:4d}  {bar}")

    print("\nIndustry group distribution:")
    rows = query(conn, """
        SELECT industry_group, COUNT(*) AS cnt
        FROM edgar_filings
        GROUP BY industry_group ORDER BY cnt DESC
        LIMIT 15
    """)
    for ig, cnt in rows:
        print(f"  {cnt:4d}  {ig or '(empty)'}")

    zero_amount = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE amount_raised = 0")[0][0]
    if zero_amount:
        print(f"\nANOMALY: {zero_amount} filings with amount_raised=0 (undisclosed)")


def validate_matches(conn):
    section("ACCELERATOR × EDGAR MATCHES")

    matches = query(conn, """
        SELECT
            e.company_name,
            a.name AS acc_name,
            a.accelerator,
            a.batch,
            a.website,
            e.date_filed,
            e.amount_raised,
            e.industry_group
        FROM edgar_filings e
        JOIN accelerator_companies a ON e.accelerator_id = a.id
        WHERE (e.amount_raised IS NULL OR e.amount_raised <= 100000000)
          AND a.is_excluded = FALSE
        ORDER BY e.date_filed DESC
    """)

    print(f"Total confirmed matches: {len(matches)}")

    if not matches:
        print("  (none yet — run scrapers/cik_lookup.py then scrapers/edgar.py --mode targeted)")
    else:
        print(f"\n  {'EDGAR Name':<40} {'Acc Name':<35} {'Acc':<8} {'Batch':<10} {'Filed':<12} {'Amount':>12}")
        print(f"  {'-'*40} {'-'*35} {'-'*8} {'-'*10} {'-'*12} {'-'*12}")
        for company_name, acc_name, acc, batch, website, filed, amount, ig in matches:
            amount_str = f"${amount:,.0f}" if amount else "N/A"
            print(f"  {(company_name or '')[:40]:<40} {(acc_name or '')[:35]:<35} {acc:<8} {(batch or '')[:10]:<10} {str(filed or ''):<12} {amount_str:>12}")

    validate_acceptance_criteria(conn)


def validate_acceptance_criteria(conn):
    section("ACCEPTANCE CRITERIA CHECK")

    total_acc = query(conn, "SELECT COUNT(*) FROM accelerator_companies")[0][0]
    total_edgar = query(conn, "SELECT COUNT(*) FROM edgar_filings")[0][0]
    match_total = query(conn, "SELECT COUNT(*) FROM edgar_filings e JOIN accelerator_companies a ON e.accelerator_id = a.id WHERE (e.amount_raised IS NULL OR e.amount_raised <= 100000000) AND a.is_excluded = FALSE")[0][0]
    cik_coverage = query(conn, "SELECT COUNT(*) FROM accelerator_companies WHERE edgar_cik IS NOT NULL")[0][0]

    accs = query(conn, "SELECT COUNT(DISTINCT accelerator) FROM accelerator_companies")[0][0]

    if total_edgar > 0:
        with_amount = query(conn, "SELECT COUNT(*) FROM edgar_filings WHERE amount_raised IS NOT NULL AND amount_raised > 0")[0][0]
        pct_amount = with_amount / total_edgar * 100
    else:
        pct_amount = 0

    checks = [
        ("Accelerator DB has >= 500 companies", total_acc >= 500, f"{total_acc} companies"),
        ("Accelerator DB covers >= 3 sources", accs >= 3, f"{accs} accelerators"),
        ("EDGAR has >= 200 filings", total_edgar >= 200, f"{total_edgar} filings"),
        (">=60% filings have amount_raised", pct_amount >= 60, f"{pct_amount:.1f}%"),
        (">=1 accelerator company matched to EDGAR filing", match_total >= 1, f"{match_total} matches"),
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
        print("\nSome criteria not yet met.")


def validate_careers(conn):
    section("CAREERS DATA")

    total_scraped = query(conn, "SELECT COUNT(*) FROM accelerator_companies WHERE careers_scraped_at IS NOT NULL AND is_excluded = FALSE")[0][0]
    if total_scraped == 0:
        print("  (no data — run scrapers/careers.py first)")
        return

    found = query(conn, "SELECT COUNT(*) FROM accelerator_companies WHERE careers_ats != 'not_found' AND careers_ats IS NOT NULL AND is_excluded = FALSE")[0][0]
    not_found = query(conn, "SELECT COUNT(*) FROM accelerator_companies WHERE careers_ats = 'not_found' AND is_excluded = FALSE")[0][0]
    print(f"Companies scraped: {total_scraped}  |  ATS found: {found}  |  Not found: {not_found}")

    print("\nBy ATS:")
    rows = query(conn, """
        SELECT careers_ats, COUNT(*) FROM accelerator_companies
        WHERE careers_ats IS NOT NULL AND careers_ats != 'not_found'
        GROUP BY careers_ats ORDER BY COUNT(*) DESC
    """)
    for ats, cnt in rows:
        print(f"  {ats:<12} {cnt}")

    total_jobs = query(conn, "SELECT COUNT(*) FROM job_listings")[0][0]
    print(f"\nTotal job listings: {total_jobs}")

    print("\nRole category breakdown:")
    rows = query(conn, "SELECT category, COUNT(*) FROM job_listings GROUP BY category ORDER BY COUNT(*) DESC")
    for cat, cnt in rows:
        print(f"  {cat:<14} {cnt}")

    print("\nHiring composition per matched company (top 20 by total jobs):")
    rows = query(conn, """
        SELECT
            a.name,
            COUNT(*) AS total,
            SUM(CASE WHEN j.category = 'engineering' THEN 1 ELSE 0 END) AS eng,
            SUM(CASE WHEN j.category = 'product' THEN 1 ELSE 0 END) AS product,
            SUM(CASE WHEN j.category = 'gtm' THEN 1 ELSE 0 END) AS gtm,
            SUM(CASE WHEN j.category = 'other' THEN 1 ELSE 0 END) AS other
        FROM job_listings j
        JOIN accelerator_companies a ON j.company_id = a.id
        GROUP BY a.name ORDER BY total DESC
        LIMIT 20
    """)
    print(f"  {'Company':<30} {'Total':>6} {'Eng':>5} {'Prod':>5} {'GTM':>5} {'Other':>6}")
    print(f"  {'-'*30} {'-'*6} {'-'*5} {'-'*5} {'-'*5} {'-'*6}")
    for name, total, eng, prod, gtm, other in rows:
        print(f"  {name[:30]:<30} {total:>6} {eng:>5} {prod:>5} {gtm:>5} {other:>6}")


def main():
    conn = get_connection()
    try:
        validate_accelerator_companies(conn)
        validate_edgar(conn)
        validate_matches(conn)
        validate_careers(conn)
    finally:
        conn.close()

    print("\n")


if __name__ == "__main__":
    main()
