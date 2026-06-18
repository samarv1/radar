"""
EDGAR CIK lookup for accelerator companies.

For each accelerator_company with no edgar_cik, searches EDGAR's full-text
search API by company name. Stores the CIK and confidence level.

Confidence levels:
  exact  - normalized name match score >= 95
  fuzzy  - score 80–94 (flag for manual review)
  (NULL) - no match found; company likely hasn't filed Form D yet

Usage:
    uv run python scrapers/cik_lookup.py [--limit 200] [--refetch-fuzzy]
"""

import re
import sys
import time

import requests
from rapidfuzz import fuzz

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

EFTS = "https://efts.sec.gov/LATEST/search-index"
HEADERS = {
    "User-Agent": "startup-recruiting-tool contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}
SLEEP = 0.2
EXACT_THRESHOLD = 95
FUZZY_THRESHOLD = 80

LEGAL_SUFFIXES = re.compile(
    r"\b(inc|llc|corp|ltd|co|incorporated|limited|company|technologies|technology|"
    r"solutions|software|labs|lab|studio|studios|ai|io|app|apps|group|ventures|"
    r"holdings|capital|partners|fund|management|pbc)\b",
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


def search_edgar(company_name: str) -> list[dict]:
    """
    Search EDGAR EFTS for Form D filings matching the company name.
    Returns list of {cik, entity_name, file_date}.
    """
    params = {"q": f'"{company_name}"', "forms": "D"}
    try:
        resp = requests.get(EFTS, params=params, headers=HEADERS, timeout=20)
        time.sleep(SLEEP)
        if resp.status_code != 200:
            return []
        hits = resp.json().get("hits", {}).get("hits", [])
    except Exception:
        return []

    results = []
    for hit in hits:
        src = hit.get("_source", {})
        ciks = src.get("ciks", [])
        if not ciks:
            continue
        display_names = src.get("display_names", [])
        entity_name = display_names[0].split("(CIK")[0].strip() if display_names else ""
        results.append({
            "cik": ciks[0].lstrip("0"),
            "entity_name": entity_name,
            "file_date": src.get("file_date", ""),
        })

    return results


def best_match(company_name: str, candidates: list[dict]) -> tuple[str | None, str | None, float]:
    """
    Returns (cik, entity_name, score) for the best matching candidate.
    """
    norm_query = normalize(company_name)
    if not norm_query:
        return None, None, 0

    best_cik = best_name = None
    best_score = 0.0

    for c in candidates:
        norm_candidate = normalize(c["entity_name"])
        score = fuzz.token_sort_ratio(norm_query, norm_candidate)
        if score > best_score:
            best_score = score
            best_cik = c["cik"]
            best_name = c["entity_name"]

    return best_cik, best_name, best_score


def store_cik(conn, company_id: int, cik: str, confidence: str):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE accelerator_companies SET edgar_cik = %s, cik_confidence = %s, updated_at = NOW() WHERE id = %s",
            (cik, confidence, company_id),
        )


def run(limit: int = 500, refetch_fuzzy: bool = False):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if refetch_fuzzy:
                cur.execute(
                    "SELECT id, name FROM accelerator_companies WHERE edgar_cik IS NULL OR cik_confidence = 'fuzzy' ORDER BY id LIMIT %s",
                    (limit,),
                )
            else:
                cur.execute(
                    "SELECT id, name FROM accelerator_companies WHERE edgar_cik IS NULL ORDER BY id LIMIT %s",
                    (limit,),
                )
            companies = cur.fetchall()

        print(f"Looking up CIKs for {len(companies)} companies...")
        exact = fuzzy_count = not_found = failed = 0

        for i, (company_id, name) in enumerate(companies):
            print(f"[{i+1}/{len(companies)}] {name}", end="")

            candidates = search_edgar(name)
            if not candidates:
                print(" — not found")
                not_found += 1
                continue

            cik, matched_name, score = best_match(name, candidates)

            if score >= EXACT_THRESHOLD:
                store_cik(conn, company_id, cik, "exact")
                conn.commit()
                exact += 1
                print(f" — exact (score={score:.0f}) CIK={cik} → '{matched_name}'")
            elif score >= FUZZY_THRESHOLD:
                store_cik(conn, company_id, cik, "fuzzy")
                conn.commit()
                fuzzy_count += 1
                print(f" — fuzzy (score={score:.0f}) CIK={cik} → '{matched_name}' [REVIEW]")
            else:
                print(f" — no confident match (best={score:.0f} → '{matched_name}')")
                not_found += 1

    finally:
        conn.close()

    print(f"\nDone. Exact: {exact}, Fuzzy: {fuzzy_count}, Not found: {not_found}, Failed: {failed}")
    print(f"Run with --refetch-fuzzy to retry fuzzy matches after manual review.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--refetch-fuzzy", action="store_true")
    args = parser.parse_args()

    run(limit=args.limit, refetch_fuzzy=args.refetch_fuzzy)
