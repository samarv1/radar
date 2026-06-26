"""
Crunchbase News funding scraper.

Fetches articles from Crunchbase News via the WordPress REST API (Funding reports
category), parses company name / amount / round, cross-references with
accelerator_companies, and upserts into funding_news.

Usage:
    uv run python scrapers/crunchbase_news.py [--days 90]
"""

import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from rapidfuzz import fuzz, process

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection
from scrapers.techcrunch import (
    FUNDING_KEYWORDS, ROUND_RE, AMOUNT_RE,
    normalize, find_match, load_accelerator_index,
    parse_amount, parse_round, parse_company, strip_tags,
)

WP_API = "https://news.crunchbase.com/wp-json/wp/v2/posts"
# Category IDs on Crunchbase News: 6=Funding reports, 2039=Seed funding, 2=Startups
FUNDING_CATEGORIES = [6, 2039]
HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}
SLEEP = 0.4

# CBN title patterns: "Flip Raises $20M Series A", "AppsFlyer Reportedly Lands $1B"
CBN_SPLIT_RE = re.compile(
    r"\s+(?:raises?|closes?|secures?|lands?|gets?|wins?|reportedly|has raised|announces?)\b",
    re.IGNORECASE,
)


def parse_company_cbn(title: str) -> str | None:
    """Extract company name from CBN title (e.g. 'Flip Raises $20M Series A' → 'Flip')."""
    title = html.unescape(title)
    # Strip leading descriptor prefixes after comma or colon
    for sep in (",", ":"):
        if sep in title:
            title = title.rsplit(sep, 1)[-1].strip()
            break
    parts = CBN_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) < 2:
        # Fall back to generic parser
        return parse_company(title)
    name = parts[0].strip().strip("'\"").strip()
    # Drop trailing parentheticals like "(YC W24)"
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if not name or len(name) > 60:
        return None
    return name


def fetch_posts(days_back: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%S")
    posts: list[dict] = []

    for category_id in FUNDING_CATEGORIES:
        page = 1
        while True:
            params = {
                "categories": category_id,
                "per_page": 100,
                "page": page,
                "after": cutoff,
                "_fields": "id,title,date,link,content",
            }
            resp = requests.get(WP_API, params=params, headers=HEADERS, timeout=30)
            time.sleep(SLEEP)

            if resp.status_code == 400:
                break
            resp.raise_for_status()

            batch = resp.json()
            if not batch:
                break

            if page == 1:
                total = resp.headers.get("X-WP-Total", "?")
                print(f"  Category {category_id}: {total} posts in window")

            posts.extend(batch)
            page += 1

    # Deduplicate by article id
    seen: set[int] = set()
    unique = []
    for p in posts:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)
    return unique


def upsert(conn, row: dict) -> bool:
    sql = """
        INSERT INTO funding_news
            (company_name, amount_usd, round_type, article_title, article_url,
             published_at, source, accelerator_id, website)
        VALUES
            (%(company_name)s, %(amount_usd)s, %(round_type)s, %(article_title)s,
             %(article_url)s, %(published_at)s, 'crunchbase_news', %(accelerator_id)s, %(website)s)
        ON CONFLICT (article_url) DO UPDATE SET
            accelerator_id = COALESCE(funding_news.accelerator_id, EXCLUDED.accelerator_id),
            company_name = EXCLUDED.company_name,
            website = COALESCE(funding_news.website, EXCLUDED.website)
        RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
        result = cur.fetchone()
        return result[0] if result else False


def scrape(days_back: int = 90):
    print(f"Fetching Crunchbase News funding posts (last {days_back} days)...")
    posts = fetch_posts(days_back)
    print(f"Fetched {len(posts)} posts total (deduplicated)")

    funding_posts = [p for p in posts if FUNDING_KEYWORDS.search(p["title"]["rendered"])]
    print(f"Funding-related: {len(funding_posts)}")

    conn = get_connection()
    try:
        ids, names_norm = load_accelerator_index(conn)
        inserted = updated = skipped = matched = 0

        for p in funding_posts:
            title = html.unescape(p["title"]["rendered"])
            content_html = p.get("content", {}).get("rendered", "")

            company = parse_company_cbn(title)
            if not company:
                skipped += 1
                continue

            amount = parse_amount(title)
            body_text = strip_tags(content_html[:1500]) if content_html else ""
            round_type = parse_round(title, body_text)
            acc_id = find_match(company, ids, names_norm)
            if acc_id:
                matched += 1

            row = {
                "company_name": company,
                "amount_usd": amount,
                "round_type": round_type,
                "article_title": title,
                "article_url": p["link"],
                "published_at": p["date"],
                "accelerator_id": acc_id,
                "website": None,
            }

            is_new = upsert(conn, row)
            tag = " [ACC MATCH]" if acc_id else ""
            amount_str = f"${amount/1e6:.1f}M" if amount else "?"
            print(f"  {'NEW' if is_new else 'UPD'}  {company[:35]:<35}  {round_type or '?':<10}  {amount_str:>8}{tag}")
            if is_new:
                inserted += 1
            else:
                updated += 1

        conn.commit()
    finally:
        conn.close()

    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Skipped (no parse): {skipped}, Matched to accelerator: {matched}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90, help="How many days back to fetch")
    args = parser.parse_args()
    scrape(days_back=args.days)
