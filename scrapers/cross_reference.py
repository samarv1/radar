"""
Cross-reference EDGAR filings with YC companies using fuzzy matching.

Normalizes company names, runs batch fuzzy matching via rapidfuzz,
and stores matches above the threshold in the `matches` table.

Usage:
    uv run python scrapers/cross_reference.py
"""

import re
import sys

from rapidfuzz import process, fuzz

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

MATCH_THRESHOLD = 85  # minimum score to be considered a match
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
        cur.execute("SELECT id, name FROM yc_companies")
        rows = cur.fetchall()
    return [(row[0], row[1], normalize(row[1])) for row in rows]


def upsert_match(conn, edgar_id: int, yc_id: int, score: float):
    sql = """
        INSERT INTO matches (edgar_id, yc_id, match_score)
        VALUES (%s, %s, %s)
        ON CONFLICT (edgar_id, yc_id) DO UPDATE SET match_score = EXCLUDED.match_score
    """
    with conn.cursor() as cur:
        cur.execute(sql, (edgar_id, yc_id, score))


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

            # rapidfuzz: find best match against all YC normalized names
            results = process.extract(
                edgar_norm,
                yc_names_norm,
                scorer=fuzz.token_sort_ratio,
                limit=5,
                score_cutoff=MATCH_THRESHOLD,
            )

            for matched_norm, score, idx in results:
                yc_id = yc_ids[idx]
                yc_orig = yc_names_orig[idx]
                upsert_match(conn, edgar_id, yc_id, score)
                total_matches += 1

                flag = ""
                if score <= AMBIGUOUS_ZONE_MAX:
                    flag = " [REVIEW]"
                    ambiguous.append((score, edgar_orig, yc_orig))

                print(f"  Match (score={score:.0f}){flag}: '{edgar_orig}' <-> '{yc_orig}'")

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
