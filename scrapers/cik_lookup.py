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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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
TICKER = re.compile(r"\s*\([A-Z][A-Z0-9\s,]*\)")  # strips "(ABNB)", "(RGTI, RGTIW)", etc.
PUNCTUATION = re.compile(r"[^\w\s]")
WHITESPACE = re.compile(r"\s+")


def normalize(name: str) -> str:
    name = TICKER.sub("", name)  # remove stock tickers before lowercasing
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


_print_lock = threading.Lock()
_counters = {"exact": 0, "fuzzy": 0, "not_found": 0, "failed": 0}
_counter_lock = threading.Lock()


def _lookup_one(args):
    company_id, name, total, idx = args
    try:
        candidates = search_edgar(name)
        if not candidates:
            with _counter_lock:
                _counters["not_found"] += 1
            with _print_lock:
                print(f"[{idx}/{total}] {name} — not found")
            return

        cik, matched_name, score = best_match(name, candidates)

        if score >= EXACT_THRESHOLD:
            confidence = "exact"
        elif score >= FUZZY_THRESHOLD:
            confidence = "fuzzy"
        else:
            with _counter_lock:
                _counters["not_found"] += 1
            with _print_lock:
                print(f"[{idx}/{total}] {name} — no confident match (best={score:.0f} → '{matched_name}')")
            return

        conn = get_connection()
        try:
            store_cik(conn, company_id, cik, confidence)
            conn.commit()
        finally:
            conn.close()

        with _counter_lock:
            _counters[confidence] += 1
        with _print_lock:
            tag = "[REVIEW]" if confidence == "fuzzy" else ""
            print(f"[{idx}/{total}] {name} — {confidence} (score={score:.0f}) CIK={cik} → '{matched_name}' {tag}")

    except Exception as e:
        with _counter_lock:
            _counters["failed"] += 1
        with _print_lock:
            print(f"[{idx}/{total}] {name} — error: {e}")


def run(limit: int = 500, refetch_fuzzy: bool = False, workers: int = 5):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            order = """
                ORDER BY
                  CASE
                    WHEN CAST(SUBSTRING(batch FROM '\\d{4}') AS INTEGER) BETWEEN 2022 AND 2025 THEN 0
                    WHEN CAST(SUBSTRING(batch FROM '\\d{4}') AS INTEGER) < 2022 THEN 1
                    ELSE 2
                  END,
                  CAST(SUBSTRING(batch FROM '\\d{4}') AS INTEGER) DESC NULLS LAST,
                  CASE WHEN batch LIKE 'Summer%%' THEN 1 ELSE 0 END DESC,
                  id
            """
            if refetch_fuzzy:
                cur.execute(
                    f"SELECT id, name FROM accelerator_companies WHERE edgar_cik IS NULL OR cik_confidence = 'fuzzy' {order} LIMIT %s",
                    (limit,),
                )
            else:
                cur.execute(
                    f"SELECT id, name FROM accelerator_companies WHERE edgar_cik IS NULL {order} LIMIT %s",
                    (limit,),
                )
            companies = cur.fetchall()
    finally:
        conn.close()

    total = len(companies)
    print(f"Looking up CIKs for {total} companies with {workers} parallel workers...")

    args = [(company_id, name, total, i + 1) for i, (company_id, name) in enumerate(companies)]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_lookup_one, args))

    print(f"\nDone. Exact: {_counters['exact']}, Fuzzy: {_counters['fuzzy']}, Not found: {_counters['not_found']}, Failed: {_counters['failed']}")
    print(f"Run with --refetch-fuzzy to retry fuzzy matches after manual review.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--refetch-fuzzy", action="store_true")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    run(limit=args.limit, refetch_fuzzy=args.refetch_fuzzy, workers=args.workers)
