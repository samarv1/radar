"""
a16z Build newsletter scraper.

Parses the a16z Build Substack RSS feed to extract early-stage startups
featured in each issue. Company names are hyperlinked to their websites in
the newsletter HTML, making extraction reliable without title parsing.

Upserts into funding_news with source='a16z_build'. Companies that fuzzy-match
an existing accelerator_companies entry get accelerator_id set (they'll appear
in the accel_announced feed branch). Others appear as None/Unknown.

Usage:
    uv run python scrapers/a16z_build.py [--days 30]
"""

import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection
from scrapers.techcrunch import normalize, find_match, load_accelerator_index

RSS_URL = "https://a16zbuild.substack.com/feed"
HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}

# Domains that are not company websites
_SKIP_DOMAINS = re.compile(
    r"(linkedin\.com|ashbyhq\.com|lever\.co|greenhouse\.io|boards\.greenhouse|"
    r"jobs\.ashby|drive\.google\.com|docs\.google\.com|x\.com|twitter\.com|"
    r"youtube\.com|instagram\.com|facebook\.com|substack\.com|a16z\.com|"
    r"bloomberg\.com|crunchbase\.com|pitchbook\.com|sec\.gov|"
    r"techcrunch\.com|reuters\.com|wsj\.com)",
    re.IGNORECASE,
)

# Words that indicate job role links or non-company links
_JOB_WORDS = {
    "engineer", "engineering", "designer", "design", "product", "manager",
    "lead", "head", "director", "developer", "scientist", "analyst",
    "marketing", "sales", "operations", "finance", "recruiting", "hr",
    "officer", "vp", "president", "cto", "ceo", "cfo", "cmo",
    "apply", "here", "role", "position", "job", "team", "fellowship",
    "internship", "intern", "contractor", "part-time", "forward",
    "deployed", "founding", "staff", "principal", "senior", "junior",
    "associate", "coordinator", "specialist", "consultant", "reach",
    "out", "email", "subscribe", "newsletter", "form", "cohort",
    "assistant", "producer", "series", "loop", "stealth",
}

# Common English function words — if any appear after the first word, it's not a company name
_FUNCTION_WORDS = {"in", "the", "a", "an", "of", "at", "for", "to", "with", "and", "or", "on", "by", "from", "its"}


class _CompanyLinks(HTMLParser):
    """Extract company name + website pairs from newsletter HTML."""

    def __init__(self):
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith("http") and not _SKIP_DOMAINS.search(href):
                self._href = href
                self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = html.unescape("".join(self._text)).strip()
            words = text.split()
            lower_words = [w.lower() for w in words]
            if (
                text
                and text[0].isupper()
                and "(" not in text         # reject "Tues (6/2)" etc.
                and 1 <= len(words) <= 3    # 3-word max avoids long phrases
                and not _JOB_WORDS.intersection(lower_words)
                and not _FUNCTION_WORDS.intersection(lower_words[1:])  # "Stay in the loop"
            ):
                self.results.append((text, self._href))
            self._href = None
            self._text = []


def extract_companies(content_html: str) -> list[tuple[str, str]]:
    """Return deduplicated list of (company_name, website_url) from newsletter HTML."""
    parser = _CompanyLinks()
    parser.feed(html.unescape(content_html))
    seen: set[str] = set()
    results = []
    for name, url in parser.results:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            results.append((name, url))
    return results


def fetch_rss(days_back: int) -> list[dict]:
    resp = requests.get(RSS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    items = []

    for item in root.findall(".//item"):
        pub_str = item.findtext("pubDate", "")
        try:
            pub_date = parsedate_to_datetime(pub_str)
        except Exception:
            continue

        # parsedate_to_datetime may return naive or aware datetime
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        if pub_date < cutoff:
            continue

        content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        items.append({
            "title": item.findtext("title", "").strip(),
            "url": item.findtext("link", "").strip(),
            "pub_date": pub_date.isoformat(),
            "content": content_el.text if content_el is not None else "",
        })

    return items


def upsert(conn, row: dict) -> bool:
    sql = """
        INSERT INTO funding_news
            (company_name, amount_usd, round_type, article_title, article_url,
             published_at, source, accelerator_id, website)
        VALUES
            (%(company_name)s, %(amount_usd)s, %(round_type)s, %(article_title)s,
             %(article_url)s, %(published_at)s, 'a16z_build', %(accelerator_id)s,
             %(website)s)
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


def scrape(days_back: int = 30):
    print(f"Fetching a16z Build newsletter (last {days_back} days)...")
    items = fetch_rss(days_back)
    print(f"Found {len(items)} newsletter issue(s)")

    conn = get_connection()
    try:
        ids, names_norm = load_accelerator_index(conn)
        inserted = updated = matched = 0
        matched_acc_ids: set[int] = set()

        for item in items:
            companies = extract_companies(item["content"])
            print(f"\n  [{item['pub_date'][:10]}] {item['title'][:60]}: {len(companies)} companies")

            for company_name, website_url in companies:
                slug = re.sub(r"[^\w]", "-", company_name.lower()).strip("-")
                article_url = f"{item['url']}#{slug}"

                acc_id = find_match(company_name, ids, names_norm)
                if acc_id:
                    matched += 1
                    matched_acc_ids.add(acc_id)

                row = {
                    "company_name": company_name,
                    "amount_usd": None,
                    "round_type": None,
                    "article_title": item["title"],
                    "article_url": article_url,
                    "published_at": item["pub_date"],
                    "accelerator_id": acc_id,
                    "website": website_url,
                }

                is_new = upsert(conn, row)
                tag = " [ACC MATCH]" if acc_id else ""
                print(f"    {'NEW' if is_new else 'UPD'}  {company_name[:40]:<40}{tag}")
                if is_new:
                    inserted += 1
                else:
                    updated += 1

        # Reset careers_scraped_at for matched companies so the next careers
        # sweep re-scrapes them promptly (they're confirmed to be hiring now).
        if matched_acc_ids:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE accelerator_companies SET careers_scraped_at = NULL WHERE id = ANY(%s)",
                    (list(matched_acc_ids),),
                )
            print(f"\n  Reset careers_scraped_at for {len(matched_acc_ids)} matched companies")

        conn.commit()
    finally:
        conn.close()

    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Matched to accelerator: {matched}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    scrape(days_back=args.days)
