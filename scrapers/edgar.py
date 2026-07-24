"""
EDGAR Form D scraper.

Pulls Form D filings from the last 90 days using the EDGAR full-text search
API, pre-filters pooled investment funds at the stub level (via `items`
field), fetches primary XML for the rest, and upserts into edgar_filings.

Usage:
    uv run python scrapers/edgar.py [--days 90] [--limit 2000]
"""

import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import apply_schema, get_connection

EFTS_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

HEADERS = {
    "User-Agent": "radar-tool contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}

# Form D `items` values that indicate pooled investment funds/hedge funds
FUND_ITEMS = {"06b", "3c", "3c.1", "3c.7"}

# Industry group strings to exclude (from XML) — substring match, case-insensitive
EXCLUDED_INDUSTRY_GROUPS = {
    "Pooled Investment Fund",
    "Real Estate",
    "Residential",
    "Oil and Gas",
    "Investing",
    "Banking",  # catches "Commercial Banking", "Other Banking and Financial Services"
    "REITS",
}

SLEEP = 0.15


# ---------------------------------------------------------------------------
# 1. Stub fetching with pre-filtering
# ---------------------------------------------------------------------------

def _is_fund_stub(items: list[str]) -> bool:
    """Return True if any item indicates a pooled investment fund."""
    lowered = {i.lower() for i in items}
    return bool(lowered & FUND_ITEMS)


def search_form_d_stubs(start_date: str, end_date: str, max_stubs: int = 2000, start_offset: int = 0) -> list[dict]:
    """
    Fetch Form D filing stubs. Pre-filters fund filings by `items` field.
    Returns list of {accession_no, entity_name, file_date, cik, inc_state}.
    """
    results = []
    from_offset = start_offset
    raw_fetched = 0

    while raw_fetched < 10000:
        params = {
            "q": '""',
            "forms": "D",
            "dateRange": "custom",
            "startdt": start_date,
            "enddt": end_date,
            "from": from_offset,
        }
        try:
            resp = requests.get(EFTS_SEARCH, params=params, headers=HEADERS, timeout=30)
            time.sleep(SLEEP)
            if resp.status_code != 200:
                print(f"  EFTS {resp.status_code} at offset {from_offset}, stopping.")
                break
            data = resp.json()
        except Exception as e:
            print(f"  Request error at offset {from_offset}: {e}. Stopping.")
            break

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break

        total = data.get("hits", {}).get("total", {})
        total_value = total.get("value", 0) if isinstance(total, dict) else int(total)

        kept = 0
        for hit in hits:
            src = hit.get("_source", {})
            items = src.get("items", [])

            if _is_fund_stub(items):
                continue  # skip funds early

            ciks = src.get("ciks", [])
            cik = ciks[0] if ciks else ""
            display_names = src.get("display_names", [])
            entity_name = display_names[0].split("(CIK")[0].strip() if display_names else ""
            inc_states = src.get("inc_states", [])

            results.append({
                "accession_no": src.get("adsh", ""),
                "entity_name": entity_name,
                "file_date": src.get("file_date", ""),
                "cik": cik.lstrip("0"),  # remove leading zeros for URL path
                "inc_state": inc_states[0] if inc_states else None,
            })
            kept += 1

        raw_fetched += len(hits)
        from_offset += len(hits)
        print(f"  Scanned {raw_fetched}/{total_value} stubs, kept {len(results)} non-fund filings...")

        if len(results) >= max_stubs:
            break
        if from_offset >= total_value:
            break

    return results[:max_stubs]


# ---------------------------------------------------------------------------
# 2. XML fetching
# ---------------------------------------------------------------------------

def fetch_primary_xml(cik: str, accession_no: str) -> tuple[str | None, str | None]:
    """
    Fetch the primary Form D XML for a filing.
    Returns (xml_text, url) or (None, None).
    """
    accession_path = accession_no.replace("-", "")
    base = f"{EDGAR_ARCHIVES}/{cik}/{accession_path}"
    xml_candidates = []

    # Try the filing index JSON first to get the real filename
    try:
        idx_resp = requests.get(
            f"{base}/{accession_path}-index.json", headers=HEADERS, timeout=20
        )
        time.sleep(SLEEP)
        if idx_resp.status_code == 200:
            for item in idx_resp.json().get("directory", {}).get("item", []):
                name = item.get("name", "")
                if name.lower().endswith(".xml"):
                    xml_candidates.append(f"{base}/{name}")
    except Exception:
        pass

    # Fallback: common Form D XML names
    xml_candidates += [
        f"{base}/primary_doc.xml",
        f"{base}/{accession_no}.xml",
        f"{base}/formD.xml",
    ]

    for url in xml_candidates:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            time.sleep(SLEEP)
            if resp.status_code == 200 and "<" in resp.text:
                return resp.text, url
        except Exception:
            pass

    return None, None


# ---------------------------------------------------------------------------
# 3. XML parsing
# ---------------------------------------------------------------------------

NS_RE = re.compile(r'\s+xmlns[^"]*"[^"]*"|\s+xmlns[^\']*\'[^\']*\'')


def parse_form_d_xml(xml_text: str) -> dict:
    result = {
        "company_name": None,
        "state": None,
        "date_of_first_sale": None,
        "amount_raised": None,
        "industry_group": None,
        "entity_type": None,
    }
    try:
        root = ET.fromstring(NS_RE.sub("", xml_text))

        def find_text(*tags):
            for tag in tags:
                el = root.find(f".//{tag}")
                if el is not None and el.text and el.text.strip():
                    return el.text.strip()
            return None

        result["company_name"] = find_text("nameOfIssuer", "issuerName", "entityName")
        result["state"] = find_text("stateOrCountryDescription", "stateOfFormation", "stateOrCountry")
        # dateOfFirstSale is a container: <dateOfFirstSale><value>YYYY-MM-DD</value></dateOfFirstSale>
        result["date_of_first_sale"] = find_text("dateOfFirstSale/value", "firstSaleDate")
        result["entity_type"] = find_text("entityType", "issuerEntityType")
        # industryGroup is a container wrapping industryGroupType
        result["industry_group"] = find_text("industryGroupType", "industryGroup")

        amount_str = find_text("totalAmountSold", "totalOfferingAmount", "amountSold")
        if amount_str:
            try:
                result["amount_raised"] = float(amount_str.replace(",", ""))
            except ValueError:
                pass

    except ET.ParseError as e:
        print(f"    XML parse error: {e}")

    return result


def is_excluded_by_xml(parsed: dict) -> bool:
    ig = (parsed.get("industry_group") or "").strip()
    return any(ex.lower() in ig.lower() for ex in EXCLUDED_INDUSTRY_GROUPS)


# ---------------------------------------------------------------------------
# 4. Shared filing row builder + DB upsert
# ---------------------------------------------------------------------------

def _build_filing_row(
    parsed: dict,
    entity_name: str,
    accession_no: str,
    file_date: str,
    raw_url: str | None,
    *,
    inc_state: str | None = None,
    accelerator_id: int | None = None,
) -> dict:
    date_of_first_sale = None
    raw_dos = parsed.get("date_of_first_sale")
    if raw_dos:
        try:
            date_of_first_sale = datetime.strptime(raw_dos[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return {
        "company_name": parsed["company_name"] or entity_name,
        "state": parsed.get("state") or inc_state,
        "date_filed": file_date or None,
        "date_of_first_sale": date_of_first_sale,
        "amount_raised": parsed.get("amount_raised"),
        "industry_group": parsed.get("industry_group"),
        "entity_type": parsed.get("entity_type"),
        "accession_number": accession_no,
        "raw_url": raw_url,
        "accelerator_id": accelerator_id,
    }


def upsert_filing(conn, filing: dict) -> bool:
    sql = """
        INSERT INTO edgar_filings
            (company_name, state, date_filed, date_of_first_sale, amount_raised,
             industry_group, entity_type, accession_number, raw_url, accelerator_id)
        VALUES
            (%(company_name)s, %(state)s, %(date_filed)s, %(date_of_first_sale)s,
             %(amount_raised)s, %(industry_group)s, %(entity_type)s,
             %(accession_number)s, %(raw_url)s, %(accelerator_id)s)
        ON CONFLICT (accession_number) DO NOTHING
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(sql, filing)
        return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def scrape(days_back: int = 180, limit: int = 2000, start_offset: int = 0):
    print("Applying DB schema...")
    apply_schema()

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    print(f"Searching EDGAR Form D filings {start_date} → {end_date} (max non-fund stubs: {limit}, start_offset: {start_offset})...")
    stubs = search_form_d_stubs(str(start_date), str(end_date), max_stubs=limit, start_offset=start_offset)
    print(f"\nCollected {len(stubs)} non-fund stubs. Fetching XMLs...\n")

    conn = get_connection()
    inserted = 0
    skipped_excluded = 0
    skipped_duplicate = 0
    failed = 0

    try:
        for i, stub in enumerate(stubs):
            accession_no = stub["accession_no"]
            entity_name = stub.get("entity_name", "")
            file_date = stub.get("file_date", "")
            cik = stub.get("cik", "")
            inc_state = stub.get("inc_state")

            if not accession_no or not cik:
                failed += 1
                continue

            print(f"[{i+1}/{len(stubs)}] {entity_name} ({accession_no})", end="")

            xml_text, raw_url = fetch_primary_xml(cik, accession_no)
            if not xml_text:
                print(f" — no XML")
                failed += 1
                continue

            parsed = parse_form_d_xml(xml_text)

            if is_excluded_by_xml(parsed):
                print(f" — excluded ({parsed.get('industry_group')})")
                skipped_excluded += 1
                continue

            filing_row = _build_filing_row(parsed, entity_name, accession_no, file_date, raw_url, inc_state=inc_state)

            if upsert_filing(conn, filing_row):
                inserted += 1
                print(f" — inserted ✓")
            else:
                skipped_duplicate += 1
                print(f" — duplicate")

            conn.commit()

    finally:
        conn.close()

    print(f"\nDone. inserted={inserted}, duplicates={skipped_duplicate}, excluded={skipped_excluded}, failed={failed}")


def scrape_chunked(days_back: int = 180, chunk_days: int = 30, limit_per_chunk: int = 2000):
    """
    Broad scan split into sub-windows to stay under EDGAR's hard 10k pagination cap.
    Each window covers `chunk_days` days; windows walk backwards from today.
    ON CONFLICT DO NOTHING makes overlapping edges idempotent.
    """
    apply_schema()
    end = date.today()
    start_outer = end - timedelta(days=days_back)

    total_inserted = total_dupes = total_excluded = total_failed = 0
    window_end = end

    while window_end > start_outer:
        window_start = max(window_end - timedelta(days=chunk_days), start_outer)
        print(f"\n--- Window {window_start} → {window_end} ---")

        stubs = search_form_d_stubs(str(window_start), str(window_end), max_stubs=limit_per_chunk)
        print(f"Collected {len(stubs)} non-fund stubs. Fetching XMLs...")

        conn = get_connection()
        inserted = dupes = excluded = failed = 0
        try:
            for i, stub in enumerate(stubs):
                accession_no = stub["accession_no"]
                entity_name = stub.get("entity_name", "")
                file_date = stub.get("file_date", "")
                cik = stub.get("cik", "")
                inc_state = stub.get("inc_state")

                if not accession_no or not cik:
                    failed += 1
                    continue

                xml_text, raw_url = fetch_primary_xml(cik, accession_no)
                if not xml_text:
                    failed += 1
                    continue

                parsed = parse_form_d_xml(xml_text)
                if is_excluded_by_xml(parsed):
                    excluded += 1
                    continue

                filing_row = _build_filing_row(parsed, entity_name, accession_no, file_date, raw_url, inc_state=inc_state)

                if upsert_filing(conn, filing_row):
                    inserted += 1
                    print(f"  [{i+1}] {entity_name} — inserted ✓")
                else:
                    dupes += 1

                conn.commit()
        finally:
            conn.close()

        print(f"Window done. inserted={inserted}, dupes={dupes}, excluded={excluded}, failed={failed}")
        total_inserted += inserted
        total_dupes += dupes
        total_excluded += excluded
        total_failed += failed

        window_end = window_start

    print(f"\nChunked scan complete. inserted={total_inserted}, dupes={total_dupes}, excluded={total_excluded}, failed={total_failed}")


_targeted_print_lock = threading.Lock()

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"


def _targeted_one(acc_id: int, name: str, cik: str, cutoff: date) -> tuple[int, int, int]:
    """Fetch one company's filing history and upsert any Form D within cutoff.
    Returns (inserted, skipped, failed)."""
    cik_padded = cik.zfill(10)
    url = SUBMISSIONS.format(cik=cik_padded)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        time.sleep(SLEEP)
        if resp.status_code != 200:
            return 0, 0, 1
        data = resp.json()
    except Exception as e:
        with _targeted_print_lock:
            print(f"  [{name}] fetch error: {e}")
        return 0, 0, 1

    filings = data.get("filings", {}).get("recent", {})
    if not filings:
        return 0, 0, 0

    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])

    inserted = skipped = 0
    conn = get_connection()
    try:
        for form, filed_str, accession_no in zip(forms, dates, accessions):
            if form not in ("D", "D/A"):
                continue
            try:
                filed = datetime.strptime(filed_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if filed < cutoff:
                continue

            # Normalize accession: add dashes if missing
            accession_no = accession_no.replace("-", "")
            accession_no = f"{accession_no[:10]}-{accession_no[10:12]}-{accession_no[12:]}"

            # Fetch XML for this filing
            xml_text, raw_url = fetch_primary_xml(cik, accession_no)
            if not xml_text:
                continue

            parsed = parse_form_d_xml(xml_text)
            if is_excluded_by_xml(parsed):
                continue

            filing_row = _build_filing_row(parsed, name, accession_no, filed_str, raw_url, accelerator_id=acc_id)

            if upsert_filing(conn, filing_row):
                inserted += 1
                with _targeted_print_lock:
                    print(f"  [{name}] NEW filing {accession_no} filed {filed_str} amount={parsed.get('amount_raised')}")
            else:
                # Update accelerator_id on existing record if not set
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE edgar_filings SET accelerator_id = %s WHERE accession_number = %s AND accelerator_id IS NULL",
                        (acc_id, accession_no),
                    )
                skipped += 1

            conn.commit()
    finally:
        conn.close()

    return inserted, skipped, 0


def scrape_targeted(days_back: int = 180, workers: int = 4):
    """
    Targeted mode: for each accelerator_company with a known CIK, fetch
    their filing history from data.sec.gov and upsert any Form D filings
    from the last `days_back` days. Much faster than the broad scan and
    surgically accurate — no fuzzy matching needed.

    Parallelized across `workers` threads — each does its own request + a
    SLEEP pause, so throughput stays well under SEC's 10 req/s fair-access
    limit (workers=4 keeps it in the ~7 req/s range).
    """
    cutoff = date.today() - timedelta(days=days_back)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, edgar_cik FROM accelerator_companies WHERE edgar_cik IS NOT NULL ORDER BY id"
            )
            companies = cur.fetchall()
    finally:
        conn.close()

    print(f"Targeted scan: {len(companies)} companies with known CIKs (cutoff {cutoff}, workers={workers})")
    inserted = skipped = failed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_targeted_one, acc_id, name, cik, cutoff) for acc_id, name, cik in companies]
        for future in as_completed(futures):
            i, s, f = future.result()
            inserted += i
            skipped += s
            failed += f

    print(f"\nTargeted scan done. New filings: {inserted}, Already known: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["broad", "targeted", "chunked"], default="broad")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--limit", type=int, default=2000, help="Max non-fund stubs (broad mode)")
    parser.add_argument("--from-offset", type=int, default=0, help="EFTS start offset (broad mode)")
    parser.add_argument("--chunk-days", type=int, default=30, help="Days per window (chunked mode)")
    args = parser.parse_args()

    if args.mode == "targeted":
        scrape_targeted(days_back=args.days)
    elif args.mode == "chunked":
        scrape_chunked(days_back=args.days, chunk_days=args.chunk_days)
    else:
        scrape(days_back=args.days, limit=args.limit, start_offset=args.from_offset)
