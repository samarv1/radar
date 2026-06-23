"""
TechCrunch funding news scraper.

Fetches articles from TechCrunch's Venture category via the WordPress REST API,
filters to funding announcements by title keyword, parses company name/amount/round,
cross-references with accelerator_companies by fuzzy name match, and upserts
into funding_news.

Usage:
    uv run python scrapers/techcrunch.py [--days 90]
"""

import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import requests
from rapidfuzz import fuzz, process

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

WP_API = "https://techcrunch.com/wp-json/wp/v2/posts"
VENTURE_CATEGORY = 577030455
HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}
SLEEP = 0.3

FUNDING_KEYWORDS = re.compile(
    r"\braises?\b|\bcloses?\b|\bsecures?\b|\blands?\b|\bgets?\b|\bwins?\b|\braising\b|\bfunding\b|\binvestment\b|\bseed\b|\bseries [a-e]\b",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*(million|billion|[MB])\b", re.IGNORECASE)
ROUND_RE = re.compile(r"\b(pre-?seed|seed|series [a-e])\b", re.IGNORECASE)

COMPANY_STOPWORDS = re.compile(
    r"\b(source|report|exclusive|breaking|the|a|an)\b:?\s*", re.IGNORECASE
)

SPLIT_RE = re.compile(
    r"\s+(?:raises?|closes?|secures?|lands?|gets?|wins?|reportedly|has raised|will raise|announces?)\b",
    re.IGNORECASE,
)

# Same verbs in hyphenated slug form for URL-based parsing
SLUG_SPLIT_RE = re.compile(
    r"-(?:raises?|closes?|secures?|lands?|gets?|wins?|reportedly|has-raised|will-raise|announces?)-",
    re.IGNORECASE,
)

LEGAL_SUFFIXES = re.compile(
    r"\b(inc|llc|corp|ltd|co|incorporated|limited|company|technologies|technology|"
    r"solutions|software|labs|lab|studio|studios|ai|io|app|apps|group|ventures|"
    r"holdings|capital|partners|fund|management)\b",
    re.IGNORECASE,
)
PUNCTUATION = re.compile(r"[^\w\s]")
WHITESPACE = re.compile(r"\s+")


# Domains that are media outlets, databases, or platforms — not company websites
_SKIP_DOMAINS = re.compile(
    r"(bloomberg\.com|wsj\.com|reuters\.com|forbes\.com|nytimes\.com|"
    r"prnewswire\.com|businesswire\.com|crunchbase\.com|pitchbook\.com|"
    r"linkedin\.com|twitter\.com|x\.com|youtube\.com|facebook\.com|"
    r"instagram\.com|wikipedia\.org|pewresearch\.org|sec\.gov|"
    r"techcrunch\.com|apnews\.com|cnbc\.com|wired\.com|theinformation\.com)",
    re.IGNORECASE,
)


class _FirstExternalLink(HTMLParser):
    """Finds the first hyperlink that looks like a company website in article HTML."""

    def __init__(self):
        super().__init__()
        self.result: str | None = None
        self.website: str | None = None
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a" and self.result is None:
            href = dict(attrs).get("href", "")
            if (
                href.startswith("http")
                and "techcrunch.com" not in href
                and not _SKIP_DOMAINS.search(href)
            ):
                self._href = href
                self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            text = "".join(self._text).strip()
            words = text.split()
            _BAD_WORDS = {"announced", "launched", "raised", "said", "told",
                          "report", "source", "post", "release", "press",
                          "data", "research", "study", "according", "per"}
            # Must start uppercase and contain no non-company verb/noun words
            if (text and text[0].isupper() and 1 <= len(words) <= 4
                    and not _BAD_WORDS.intersection(w.lower() for w in words)):
                self.result = text
                self.website = self._href
            self._href = None
            self._text = []


def parse_company_from_content(content_html: str) -> str | None:
    """Extract company name from first external hyperlink in article body."""
    # Only scan the opening ~3000 chars (first few paragraphs)
    parser = _FirstExternalLink()
    parser.feed(html.unescape(content_html[:3000]))
    return parser.result


def parse_website_from_content(content_html: str) -> str | None:
    """Extract company website URL from first external hyperlink in article body."""
    parser = _FirstExternalLink()
    parser.feed(html.unescape(content_html[:3000]))
    return parser.website


def normalize(name: str) -> str:
    name = name.lower()
    name = PUNCTUATION.sub(" ", name)
    name = LEGAL_SUFFIXES.sub(" ", name)
    name = WHITESPACE.sub(" ", name).strip()
    return name


def parse_amount(title: str) -> float | None:
    m = AMOUNT_RE.search(title)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).upper()
    if unit in ("BILLION", "B"):
        value *= 1_000_000_000
    else:
        value *= 1_000_000
    return value


def parse_round(title: str) -> str | None:
    m = ROUND_RE.search(title)
    if not m:
        return None
    r = m.group(1).lower()
    if "pre" in r:
        return "Pre-Seed"
    if r == "seed":
        return "Seed"
    return f"Series {r[-1].upper()}"


def parse_company_from_slug(url: str) -> str | None:
    """Extract company name from TC URL slug — more reliable than title parsing.
    e.g. https://techcrunch.com/2026/04/02/gateway-capital-announces-first-close-25m/
    → slug: gateway-capital-announces-first-close-25m
    → split on -announces- → gateway-capital → Gateway Capital
    """
    m = re.search(r"/(\d{4}/\d{2}/\d{2}/)?([^/?#]+?)/?$", url)
    if not m:
        return None
    slug = m.group(2)
    parts = SLUG_SPLIT_RE.split(slug, maxsplit=1)
    if len(parts) < 2:
        return None
    name_slug = parts[0].strip("-")
    # Title-case hyphenated slug: "nectar-social" → "Nectar Social"
    name = " ".join(w.capitalize() for w in name_slug.split("-"))
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if not name or len(name) > 60:
        return None
    return name


def parse_company(title: str) -> str | None:
    title = html.unescape(title)
    title = COMPANY_STOPWORDS.sub("", title).strip()
    parts = SPLIT_RE.split(title, maxsplit=1)
    if len(parts) < 2:
        return None
    name = parts[0].strip().strip("'\"").strip()
    # Strip descriptor prefixes in two passes:
    # Pass 1 — comma/colon split: "Riding GLP-1 boom, VITL" → "VITL"
    #   "After pivoting, Y Combinator grad Glimpse" → "Y Combinator grad Glimpse"
    if "," in name:
        name = name.rsplit(",", 1)[-1].strip()
    elif ":" in name:
        name = name.rsplit(":", 1)[-1].strip()
    # Pass 2 — last capitalized-word run (handles remaining descriptor prefix):
    #   "Y Combinator grad Glimpse" → "Glimpse"
    #   "Marketing operating system Nectar Social" → "Nectar Social"
    words = name.split()
    if len(words) > 1:
        last_cap_start = 0
        for i, w in enumerate(words):
            if i > 0 and (w[0].isupper() or w[0].isdigit()) and words[i - 1][0].islower():
                last_cap_start = i
        if last_cap_start > 0:
            candidate = " ".join(words[last_cap_start:])
            if len(candidate.split()) <= 3:
                name = candidate
    # Drop trailing parentheticals like "(YC W24)"
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if not name or len(name) > 60:
        return None
    return name


def fetch_posts(days_back: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%S")
    posts = []
    page = 1

    while True:
        params = {
            "categories": VENTURE_CATEGORY,
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
            print(f"  Total venture posts in window: {total}")

        posts.extend(batch)
        page += 1

    return posts


def load_accelerator_index(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM accelerator_companies")
        rows = cur.fetchall()
    ids = [r[0] for r in rows]
    names_norm = [normalize(r[1]) for r in rows]
    return ids, names_norm


def find_match(company_name: str, ids, names_norm) -> int | None:
    norm = normalize(company_name)
    if not norm:
        return None
    result = process.extractOne(norm, names_norm, scorer=fuzz.token_sort_ratio, score_cutoff=90)
    if result:
        _, _, idx = result
        return ids[idx]
    return None


def upsert(conn, row: dict) -> bool:
    sql = """
        INSERT INTO funding_news
            (company_name, amount_usd, round_type, article_title, article_url,
             published_at, source, accelerator_id, website)
        VALUES
            (%(company_name)s, %(amount_usd)s, %(round_type)s, %(article_title)s,
             %(article_url)s, %(published_at)s, 'techcrunch', %(accelerator_id)s, %(website)s)
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
    print(f"Fetching TechCrunch venture posts (last {days_back} days)...")
    posts = fetch_posts(days_back)
    print(f"Fetched {len(posts)} posts total")

    funding_posts = [p for p in posts if FUNDING_KEYWORDS.search(p["title"]["rendered"])]
    print(f"Funding-related: {len(funding_posts)}")

    conn = get_connection()
    try:
        ids, names_norm = load_accelerator_index(conn)
        inserted = updated = skipped = matched = 0

        for p in funding_posts:
            title = html.unescape(p["title"]["rendered"])
            content_html = p.get("content", {}).get("rendered", "")
            # Content link is most reliable (TC hyperlinks company name in first paragraph).
            # Fall back to title parsing when content link is absent or too long.
            website = parse_website_from_content(content_html)
            company = (
                parse_company_from_content(content_html)
                or parse_company(title)
                or parse_company_from_slug(p.get("link", ""))
            )
            if not company:
                skipped += 1
                continue

            amount = parse_amount(title)
            round_type = parse_round(title)
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
                "website": website,
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
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    scrape(days_back=args.days)
