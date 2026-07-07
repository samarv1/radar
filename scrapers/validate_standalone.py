"""
Validate unmatched EDGAR filings against TechCrunch and Product Hunt signals.
Sets standalone_source on edgar_filings rows that have no accelerator_id but
appear in funding_news (TechCrunch) or ph_launches (Product Hunt ≥50 votes).
TechCrunch takes priority when both match.

Usage:
    uv run python scrapers/validate_standalone.py
"""

import re
import sys

from rapidfuzz import process, fuzz

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

MATCH_THRESHOLD = 85

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


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, company_name FROM edgar_filings WHERE accelerator_id IS NULL"
            )
            edgar_rows = cur.fetchall()

        edgar = [(row[0], row[1], normalize(row[1])) for row in edgar_rows]
        print(f"Loaded {len(edgar)} unmatched EDGAR filings.")

        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_name FROM funding_news WHERE source = 'techcrunch'")
            tc_names = [row[0] for row in cur.fetchall()]
        tc_names_norm = [normalize(n) for n in tc_names]
        print(f"Loaded {len(tc_names)} TechCrunch companies.")

        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_name FROM funding_news WHERE source = 'signalbase'")
            sb_names = [row[0] for row in cur.fetchall()]
        sb_names_norm = [normalize(n) for n in sb_names]
        print(f"Loaded {len(sb_names)} Signalbase companies.")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT product_name FROM ph_launches WHERE votes_count >= 50"
            )
            ph_names = [row[0] for row in cur.fetchall()]
        ph_names_norm = [normalize(n) for n in ph_names]
        print(f"Loaded {len(ph_names)} Product Hunt launches.")

        if not edgar:
            print("Nothing to validate.")
            return

        tc_count = 0
        ph_count = 0
        sb_count = 0

        for edgar_id, edgar_orig, edgar_norm in edgar:
            if not edgar_norm.strip():
                continue

            source = None

            if tc_names_norm:
                result = process.extractOne(
                    edgar_norm,
                    tc_names_norm,
                    scorer=fuzz.token_sort_ratio,
                    score_cutoff=MATCH_THRESHOLD,
                )
                if result:
                    _, score, idx = result
                    source = "techcrunch"
                    tc_count += 1
                    print(f"  TC (score={score:.0f}): '{edgar_orig}' <-> '{tc_names[idx]}'")

            if source is None and ph_names_norm:
                result = process.extractOne(
                    edgar_norm,
                    ph_names_norm,
                    scorer=fuzz.token_sort_ratio,
                    score_cutoff=MATCH_THRESHOLD,
                )
                if result:
                    _, score, idx = result
                    source = "producthunt"
                    ph_count += 1
                    print(f"  PH (score={score:.0f}): '{edgar_orig}' <-> '{ph_names[idx]}'")

            if source is None and sb_names_norm:
                result = process.extractOne(
                    edgar_norm,
                    sb_names_norm,
                    scorer=fuzz.token_sort_ratio,
                    score_cutoff=MATCH_THRESHOLD,
                )
                if result:
                    _, score, idx = result
                    source = "signalbase"
                    sb_count += 1
                    print(f"  SB (score={score:.0f}): '{edgar_orig}' <-> '{sb_names[idx]}'")

            if source is None:
                continue

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE edgar_filings SET standalone_source = %s WHERE id = %s",
                    (source, edgar_id),
                )

        conn.commit()
        print(f"\nValidated: {tc_count} via TechCrunch, {ph_count} via Product Hunt, {sb_count} via Signalbase")

        # Mark EDGAR "Other Technology" filings directly — no external signal needed.
        # Excludes zero-dollar raises and SPV series (e.g. "Heat Safety Solutions, LLC Series 8").
        with conn.cursor() as cur:
            cur.execute(r"""
                UPDATE edgar_filings
                SET standalone_source = 'edgar'
                WHERE accelerator_id IS NULL
                  AND standalone_source IS NULL
                  AND industry_group = 'Other Technology'
                  AND amount_raised > 0
                  AND company_name !~* 'llc series \d'
            """)
            tech_count = cur.rowcount
        conn.commit()
        print(f"Marked {tech_count} 'Other Technology' EDGAR filings as standalone")

    finally:
        conn.close()


if __name__ == "__main__":
    run()
