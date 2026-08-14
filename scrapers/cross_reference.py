"""
Cross-reference EDGAR filings with YC companies using fuzzy matching.

Normalizes company names, runs batch fuzzy matching via rapidfuzz,
and stores matches above the threshold in the `matches` table.

Usage:
    uv run python -m scrapers.cross_reference
"""

import re

from rapidfuzz import process, fuzz

from db.connection import get_connection

MATCH_THRESHOLD = 85
AMBIGUOUS_ZONE_MAX = 92  # scores 85-92 flagged for manual review


LEGAL_SUFFIXES = re.compile(
    r"\b(inc|llc|corp|ltd|co|incorporated|limited|company|technologies|technology|"
    r"solutions|software|labs|lab|studio|studios|ai|io|app|apps|group|ventures|"
    r"holdings|capital|partners|fund|management)\b",
    re.IGNORECASE,
)

PUNCTUATION = re.compile(r"[^\w\s]")
WHITESPACE = re.compile(r"\s+")


def normalize(name: str) -> str:
    name = name.lower()
    name = PUNCTUATION.sub(" ", name)
    name = LEGAL_SUFFIXES.sub(" ", name)
    name = WHITESPACE.sub(" ", name).strip()
    return name


def load_edgar_companies(conn) -> list[tuple[int, str, str]]:
    """Returns list of (id, original_name, normalized_name)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, company_name FROM edgar_filings")
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


def run():
    conn = get_connection()
    try:
        edgar = load_edgar_companies(conn)
        yc = load_yc_companies(conn)

        print(f"Loaded {len(edgar)} EDGAR filings, {len(yc)} YC companies.")

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
    run()
