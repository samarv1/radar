"""
Enrich accelerator_companies.website for Lightspeed and Sequoia.

Neither scraper captures the company website URL during the main directory scrape.
This script visits each company's detail page and extracts the external website link.

Manual one-off — not part of the automated pipeline (main.py). Run by hand after
scraping Lightspeed/Sequoia.

Lightspeed: <a id="company_url" href="https://...">
Sequoia:    <a class="button button--outline-light button--small" target="_blank" href="https://...">

Usage:
    uv run python -m scrapers.enrich_websites [--accelerator lightspeed|sequoia|all]
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from db.connection import get_connection

HEADERS = {"User-Agent": "Mozilla/5.0 radar-tool contact@example.com"}
SLEEP = 0.5


def get_lightspeed_website(source_url: str) -> str | None:
    try:
        r = requests.get(source_url, headers=HEADERS, timeout=15)
        time.sleep(SLEEP)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        tag = soup.find("a", id="company_url")
        if tag and tag.get("href", "").startswith("http"):
            return tag["href"].rstrip("/")
        return None
    except Exception:
        return None


def get_sequoia_website(source_url: str) -> str | None:
    try:
        r = requests.get(source_url, headers=HEADERS, timeout=15)
        time.sleep(SLEEP)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        btn = soup.find("a", class_=re.compile(r"button--outline-light"), target="_blank")
        if btn and btn.get("href", "").startswith("http") and "sequoiacap" not in btn["href"]:
            return btn["href"].rstrip("/")
        h1 = soup.find("h1")
        if h1:
            a = h1.find("a", href=re.compile(r"^https?://(?!sequoiacap)"))
            if a:
                return a["href"].rstrip("/")
        return None
    except Exception:
        return None


def enrich(accelerator: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, source_url FROM accelerator_companies
                WHERE accelerator = %s AND website IS NULL AND source_url IS NOT NULL
                ORDER BY id
            """, (accelerator,))
            rows = cur.fetchall()
    finally:
        conn.close()

    print(f"Enriching {len(rows)} {accelerator} companies with missing website...")

    fetcher = get_lightspeed_website if accelerator == "lightspeed" else get_sequoia_website
    found = missing = 0

    for i, (cid, name, source_url) in enumerate(rows, 1):
        website = fetcher(source_url)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if website:
                    cur.execute(
                        "UPDATE accelerator_companies SET website = %s WHERE id = %s",
                        (website, cid),
                    )
                    conn.commit()
                    found += 1
                    print(f"[{i}/{len(rows)}] {name} → {website}")
                else:
                    missing += 1
                    print(f"[{i}/{len(rows)}] {name} → (no website found)")
        finally:
            conn.close()

    print(f"\nDone. Found: {found}, Missing: {missing}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--accelerator", choices=["lightspeed", "sequoia", "all"], default="all")
    args = parser.parse_args()

    targets = ["lightspeed", "sequoia"] if args.accelerator == "all" else [args.accelerator]
    for acc in targets:
        enrich(acc)
