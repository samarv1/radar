"""
Enrich edgar_filings with VC signal data parsed from Form D XML.

For each filing with raw_url but no investor_count yet, fetches the XML and extracts:
  - investor_count: totalNumberAlreadyInvested (few = institutional, many = crowdfunding)
  - vc_firm_signal: VC firm name found in director/promoter relationshipClarification text

Usage:
    uv run python scrapers/enrich_edgar.py [--all]

By default only processes un-enriched rows (investor_count IS NULL).
Pass --all to re-process everything (useful after expanding VC_FIRMS list).
"""

import re
import sys
import time
import xml.etree.ElementTree as ET
import argparse

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

HEADERS = {
    "User-Agent": "radar-tool contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}
SLEEP = 0.15

NS_RE = re.compile(r'\s+xmlns[^"]*"[^"]*"|\s+xmlns[^\']*\'[^\']*\'')

# Known tech VC firm names — substring matched against relationshipClarification text
VC_FIRMS = [
    "sequoia", "andreessen", "a16z", "benchmark", "kleiner perkins",
    "greylock", "accel", "lightspeed", "general catalyst", "nea",
    "index ventures", "bessemer", "google ventures", "gv ",
    "first round", "true ventures", "union square", "insight partners",
    "menlo ventures", "battery ventures", "tiger global", "coatue",
    "founders fund", "y combinator", "techstars", "pear vc",
    "felicis", "lux capital", "initialized capital", "haystack",
    "matrix partners", "redpoint", "ribbit", "emergence capital",
    "khosla", "spark capital", "social capital", "craft ventures",
    "founders collective", "forerunner", "floodgate", " 500 ",
    "softbank", "tiger", "dragoneer", "thrive capital",
    "lowercase capital", "collaborative fund", "slow ventures",
]


def fetch_xml(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


def parse_enrichment(xml_text: str) -> tuple[int | None, str | None, str | None]:
    """Returns (investor_count, vc_firm_signal, offering_name)."""
    try:
        root = ET.fromstring(NS_RE.sub("", xml_text))
    except ET.ParseError:
        return None, None, None

    def find_text(*tags):
        for tag in tags:
            el = root.find(f".//{tag}")
            if el is not None and el.text and el.text.strip():
                return el.text.strip()
        return None

    investor_count = None
    el = root.find(".//totalNumberAlreadyInvested")
    if el is not None and el.text:
        try:
            investor_count = int(el.text.strip())
        except ValueError:
            pass

    vc_firm_signal = None
    for person in root.findall(".//relatedPersonInfo"):
        relationships = [r.text or "" for r in person.findall(".//relationship")]
        if not any(rel in ("Director", "Promoter") for rel in relationships):
            continue
        clarification_el = person.find(".//relationshipClarification")
        if clarification_el is None or not clarification_el.text:
            # Also check the person's name itself for firm names
            first = (person.findtext(".//firstName") or "").lower()
            last = (person.findtext(".//lastName") or "").lower()
            name_text = f"{first} {last}"
            for firm in VC_FIRMS:
                if firm in name_text:
                    vc_firm_signal = firm.strip()
                    break
            continue
        clarification = clarification_el.text.lower()
        for firm in VC_FIRMS:
            if firm in clarification:
                vc_firm_signal = firm.strip()
                break
        if vc_firm_signal:
            break

    # Offering name — often contains round designation e.g. "Series A Preferred Stock"
    offering_name = find_text("nameOfOffering", "offeringName", "securityType")

    return investor_count, vc_firm_signal, offering_name


def run(reprocess_all: bool = False):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if reprocess_all:
                cur.execute(
                    "SELECT id, company_name, raw_url FROM edgar_filings WHERE raw_url IS NOT NULL"
                )
            else:
                cur.execute(
                    "SELECT id, company_name, raw_url FROM edgar_filings "
                    "WHERE raw_url IS NOT NULL AND investor_count IS NULL"
                )
            rows = cur.fetchall()

        print(f"Enriching {len(rows)} filing(s)...")

        updated = 0
        for edgar_id, company_name, raw_url in rows:
            xml_text = fetch_xml(raw_url)
            time.sleep(SLEEP)

            if not xml_text:
                print(f"  SKIP  {company_name[:40]} — fetch failed")
                continue

            investor_count, vc_firm_signal, offering_name = parse_enrichment(xml_text)

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE edgar_filings SET investor_count = %s, vc_firm_signal = %s, offering_name = %s WHERE id = %s",
                    (investor_count, vc_firm_signal, offering_name, edgar_id),
                )
            updated += 1

            vc_tag = f" ← VC: {vc_firm_signal}" if vc_firm_signal else ""
            inv_str = str(investor_count) if investor_count is not None else "?"
            off_tag = f" | {offering_name[:30]}" if offering_name else ""
            print(f"  OK    {company_name[:40]:<40}  investors={inv_str}{vc_tag}{off_tag}")

            if updated % 50 == 0:
                conn.commit()

        conn.commit()
        print(f"\nDone. Enriched {updated}/{len(rows)} filings.")

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Re-process already-enriched filings")
    args = parser.parse_args()
    run(reprocess_all=args.all)
