"""
Cross-reference EDGAR filings with accelerator companies using fuzzy matching.

Normalizes company names, runs batch fuzzy matching, and attaches confident
matches directly to the filing.

Usage:
    uv run python -m scrapers.cross_reference
"""

from rapidfuzz import process, fuzz

from db.connection import get_connection
from scrapers.company_names import normalize_company_name

MATCH_THRESHOLD = 85
AMBIGUOUS_ZONE_MAX = 92  # scores 85-92 flagged for manual review


normalize = normalize_company_name


def load_edgar_companies(conn, reprocess_all: bool = False) -> list[tuple[int, str, str]]:
    """Returns list of (id, original_name, normalized_name)."""
    with conn.cursor() as cur:
        query = "SELECT id, company_name FROM edgar_filings"
        if not reprocess_all:
            query += " WHERE accelerator_id IS NULL"
        cur.execute(query)
        rows = cur.fetchall()
    return [(row[0], row[1], normalize(row[1])) for row in rows]


def load_yc_companies(conn) -> list[tuple[int, str, str]]:
    """Returns list of (id, original_name, normalized_name)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM accelerator_companies")
        rows = cur.fetchall()
    return [(row[0], row[1], normalize(row[1])) for row in rows]


def upsert_match(conn, edgar_id: int, accelerator_id: int, score: float):
    sql = "UPDATE edgar_filings SET accelerator_id = %s WHERE id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (accelerator_id, edgar_id))


def run(reprocess_all: bool = False):
    conn = get_connection()
    try:
        edgar = load_edgar_companies(conn, reprocess_all=reprocess_all)
        yc = load_yc_companies(conn)

        print(f"Loaded {len(edgar)} EDGAR filings, {len(yc)} accelerator companies.")

        if not edgar or not yc:
            print("Nothing to match — run the scrapers first.")
            return

        yc_ids = [row[0] for row in yc]
        yc_names_orig = [row[1] for row in yc]
        yc_names_norm = [row[2] for row in yc]

        total_matches = 0
        ambiguous = []

        for edgar_id, edgar_orig, edgar_norm in edgar:
            if not edgar_norm.strip():
                continue

            result = process.extractOne(
                edgar_norm,
                yc_names_norm,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=MATCH_THRESHOLD,
            )
            if not result:
                continue

            matched_norm, score, idx = result
            accelerator_id = yc_ids[idx]
            acc_orig = yc_names_orig[idx]

            if score <= AMBIGUOUS_ZONE_MAX:
                ambiguous.append((score, edgar_orig, acc_orig))
                print(f"  Skipped ambiguous (score={score:.0f}): '{edgar_orig}' <-> '{acc_orig}' [REVIEW]")
                continue

            upsert_match(conn, edgar_id, accelerator_id, score)
            total_matches += 1
            print(f"  Match (score={score:.0f}): '{edgar_orig}' <-> '{acc_orig}'")

        conn.commit()

        print(f"\nTotal matches inserted/updated: {total_matches}")

        if ambiguous:
            print(f"\nAmbiguous matches ({MATCH_THRESHOLD}-{AMBIGUOUS_ZONE_MAX}) for manual review:")
            for score, edgar_orig, yc_orig in sorted(ambiguous, reverse=True):
                print(f"  [{score:.0f}] '{edgar_orig}' <-> '{yc_orig}'")

    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reprocess-all",
        action="store_true",
        help="Re-evaluate filings that already have an accelerator match",
    )
    args = parser.parse_args()
    run(reprocess_all=args.reprocess_all)
