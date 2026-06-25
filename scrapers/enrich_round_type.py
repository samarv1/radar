"""
Round-type enrichment for companies missing round_type.

Two-pass approach (no API keys required):
  Pass 1: Search TechCrunch by company name, apply ±180-day timing gate.
  Pass 2: Scrape company's own press/blog/news page, apply ±180-day timing gate.

Results are written to accelerator_companies.round_type.

Usage:
    uv run python scrapers/enrich_round_type.py [--limit N] [--dry-run]
"""

import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection
from scrapers.techcrunch import ROUND_RE, AMOUNT_RE, parse_round, strip_tags

WP_API = "https://techcrunch.com/wp-json/wp/v2/posts"
HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}
SLEEP = 0.5
WINDOW_DAYS = 180

DATE_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+20\d{2}\b",
    re.IGNORECASE,
)

PRESS_PATHS = ["/press", "/blog", "/news", "/newsroom", "/updates", "/media"]


def within_window(article_date_str: str, reference_date: datetime) -> bool:
    """Return True if article_date is within ±WINDOW_DAYS of reference_date."""
    try:
        dt = datetime.fromisoformat(article_date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = abs((dt - reference_date).days)
        return delta <= WINDOW_DAYS
    except Exception:
        return False


def parse_date_from_text(text: str) -> datetime | None:
    """Try to extract a publication date from freeform text."""
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0).replace(",", ""), "%B %d %Y").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def search_techcrunch(company_name: str, reference_date: datetime) -> str | None:
    """Search TC for a funding article near reference_date. Returns round type or None."""
    try:
        resp = requests.get(
            WP_API,
            params={
                "search": company_name,
                "per_page": 5,
                "_fields": "title,date,content",
            },
            headers=HEADERS,
            timeout=20,
        )
        time.sleep(SLEEP)
        if resp.status_code != 200:
            return None
        posts = resp.json()
    except Exception:
        return None

    for post in posts:
        article_date = post.get("date", "")
        if not within_window(article_date, reference_date):
            continue
        title = html.unescape(post.get("title", {}).get("rendered", ""))

        # Skip articles where the company name isn't in the title — they're about
        # other companies that merely mention this one in passing.
        if company_name.lower() not in title.lower():
            continue

        content_html = post.get("content", {}).get("rendered", "")
        body_text = strip_tags(content_html[:1500])

        # Title match: accept immediately
        round_type = parse_round(title)
        if round_type:
            return round_type

        # Body match: only accept when the round mention is within 150 chars of a
        # dollar amount — ensures it's a funding sentence, not a passing reference.
        rm = ROUND_RE.search(body_text)
        am = AMOUNT_RE.search(body_text)
        if rm and am and abs(rm.start() - am.start()) <= 150:
            r = rm.group(1).lower()
            if "pre" in r:
                return "Pre-Seed"
            if r == "seed":
                return "Seed"
            return f"Series {r[-1].upper()}"

    return None


def search_press_page(website: str, reference_date: datetime) -> str | None:
    """Try the company's own press/blog page for a funding announcement near reference_date."""
    if not website:
        return None

    base = website.rstrip("/")

    for path in PRESS_PATHS:
        url = base + path
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            time.sleep(SLEEP)
            if resp.status_code != 200:
                continue

            text = strip_tags(resp.text)
            # Split into ~500-char chunks around date mentions
            chunks = re.split(r"\n{2,}", text)
            for chunk in chunks[:60]:  # scan first 60 paragraphs
                round_type = parse_round("", chunk)
                if not round_type:
                    continue
                # Require a date in the same paragraph that's within the window.
                # Without a date anchor we can't trust the match isn't from a historical post.
                chunk_date = parse_date_from_text(chunk)
                if chunk_date and within_window(chunk_date.isoformat(), reference_date):
                    return round_type

        except Exception:
            continue

    return None


def get_companies_needing_enrichment(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                a.id,
                a.name,
                a.website,
                COALESCE(
                    (SELECT ef.date_filed::text
                     FROM edgar_filings ef
                     WHERE ef.accelerator_id = a.id
                     ORDER BY ef.date_filed DESC LIMIT 1),
                    (SELECT fn.published_at::date::text
                     FROM funding_news fn
                     WHERE fn.accelerator_id = a.id
                     ORDER BY fn.published_at DESC LIMIT 1)
                ) AS reference_date
            FROM accelerator_companies a
            WHERE a.round_type IS NULL
              AND a.is_excluded = FALSE
              AND (
                EXISTS (SELECT 1 FROM edgar_filings ef WHERE ef.accelerator_id = a.id)
                OR EXISTS (SELECT 1 FROM funding_news fn WHERE fn.accelerator_id = a.id)
              )
            ORDER BY reference_date DESC NULLS LAST
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def set_round_type(conn, company_id: int, round_type: str, dry_run: bool):
    if dry_run:
        return
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE accelerator_companies SET round_type = %s WHERE id = %s",
            (round_type, company_id),
        )
    conn.commit()


def enrich(limit: int | None = None, dry_run: bool = False):
    conn = get_connection()
    try:
        companies = get_companies_needing_enrichment(conn)
        if limit:
            companies = companies[:limit]

        print(f"Companies needing round_type enrichment: {len(companies)}")
        if dry_run:
            print("DRY RUN — no DB writes\n")

        found = 0
        for c in companies:
            name = c["name"]
            ref_str = c["reference_date"]
            if not ref_str:
                print(f"  SKIP  {name[:40]}  (no reference date)")
                continue

            reference_date = datetime.fromisoformat(ref_str).replace(tzinfo=timezone.utc)

            # Pass 1: TechCrunch search
            round_type = search_techcrunch(name, reference_date)
            source = "tc_search" if round_type else None

            # Press page scraping disabled — too many false positives from
            # JS-rendered sites where round labels appear inside bundle code.

            if round_type:
                set_round_type(conn, c["id"], round_type, dry_run)
                found += 1
                print(f"  FOUND [{source}]  {name[:40]:<40}  {round_type}")
            else:
                print(f"  MISS           {name[:40]}")

    finally:
        conn.close()

    print(f"\nEnrichment done. Found round_type for {found}/{len(companies)} companies.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max companies to process")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to DB")
    args = parser.parse_args()
    enrich(limit=args.limit, dry_run=args.dry_run)
