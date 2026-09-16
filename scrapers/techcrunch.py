"""
TechCrunch funding news scraper.

Fetches articles from TechCrunch's Venture category via the WordPress REST API,
filters to funding announcements by title keyword, parses company name/amount/round,
cross-references with accelerator_companies by fuzzy name match, and upserts
into funding_news.

Usage:
    uv run python -m scrapers.techcrunch [--days 90]
"""

import html
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import requests

from db.connection import get_connection
from scrapers.company_names import find_exact_company_match, normalize_company_identity

WP_API = "https://techcrunch.com/wp-json/wp/v2/posts"
VENTURE_CATEGORY = 577030455
HEADERS = {"User-Agent": "radar-tool contact@example.com"}
SLEEP = 0.3

FUNDING_KEYWORDS = re.compile(
    r"\braises?\b|\bcloses?\b|\bsecures?\b|\blands?\b|\bgets?\b|\bwins?\b|\braising\b|\bfunding\b|\binvestment\b|\bseed\b|\bseries [a-e]\b",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*(million|billion|[MB])\b", re.IGNORECASE)
VALUATION_BEFORE_RE = re.compile(
    r"\b(?:valued\s+at|valuation(?:\s+of)?|worth)\s*$",
    re.IGNORECASE,
)
VALUATION_AFTER_RE = re.compile(
    r"^\s*(?:(?:pre|post)-money\s+)?valuation\b",
    re.IGNORECASE,
)
ROUND_RE = re.compile(r"\b(pre-?seed|seed|series [a-e])\b", re.IGNORECASE)

COMPANY_STOPWORDS = re.compile(
    r"\b(source|report|exclusive|breaking|the|a|an)\b:?\s*", re.IGNORECASE
)

SPLIT_RE = re.compile(
    r"\s+(?:raises?|closes?|secures?|lands?|gets?|wins?|reportedly|has raised|will raise|announces?)\b",
    re.IGNORECASE,
)

SLUG_SPLIT_RE = re.compile(
    r"-(?:raises?|closes?|secures?|lands?|gets?|wins?|reportedly|has-raised|will-raise|announces?)-",
    re.IGNORECASE,
)

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
        # Only the first bare homepage is safe as a fallback; later links are often media.
        self.homepage_fallback: str | None = None
        self._first_external_seen: bool = False
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
                if not self._first_external_seen and self.homepage_fallback is None:
                    from urllib.parse import urlparse
                    path = urlparse(href).path
                    if not path or path == "/":
                        self.homepage_fallback = href
                self._first_external_seen = True

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
            if (text and text[0].isupper() and 1 <= len(words) <= 4
                    and not _BAD_WORDS.intersection(w.lower() for w in words)):
                self.result = text
                self.website = self._href
            self._href = None
            self._text = []


def parse_company_link(content_html: str) -> tuple[str | None, str | None]:
    """Extract the company name and website in one pass through the article body."""
    parser = _FirstExternalLink()
    parser.feed(html.unescape(content_html[:3000]))
    return parser.result, parser.website or parser.homepage_fallback


def parse_company_from_content(content_html: str) -> str | None:
    return parse_company_link(content_html)[0]


def parse_website_from_content(content_html: str) -> str | None:
    return parse_company_link(content_html)[1]


normalize = normalize_company_identity


def parse_amount(title: str) -> float | None:
    for match in AMOUNT_RE.finditer(title):
        before = title[max(0, match.start() - 40):match.start()]
        after = title[match.end():match.end() + 40]
        if VALUATION_BEFORE_RE.search(before) or VALUATION_AFTER_RE.search(after):
            continue

        value = float(match.group(1))
        unit = match.group(2).upper()
        if unit in ("BILLION", "B"):
            value *= 1_000_000_000
        else:
            value *= 1_000_000
        return value
    return None


def strip_tags(html_str: str) -> str:
    return re.sub(r"<[^>]+>", " ", html_str)


def parse_round(title: str, body_text: str | None = None) -> str | None:
    for text in (title, body_text or ""):
        m = ROUND_RE.search(text)
        if m:
            r = m.group(1).lower()
            if "pre" in r:
                return "Pre-Seed"
            if r == "seed":
                return "Seed"
            return f"Series {r[-1].upper()}"
    return None


def parse_company_from_slug(url: str) -> str | None:
    """Extract company name from a TC URL slug when title parsing fails.
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
    name = re.sub(r"^\$[\d.,]+\s*[BMKbmk]?\s+", "", name).strip()
    # Descriptor prefixes end at the last comma or colon.
    if "," in name:
        name = name.rsplit(",", 1)[-1].strip()
    elif ":" in name:
        name = name.rsplit(":", 1)[-1].strip()
    # A final capitalized run handles descriptors without punctuation.
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
    index = find_exact_company_match(company_name, names_norm)
    return ids[index] if index is not None else None


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
            # The first linked company name is more reliable than headline parsing.
            linked_company, website = parse_company_link(content_html)
            company = (
                linked_company
                or parse_company(title)
                or parse_company_from_slug(p.get("link", ""))
            )
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
    backfill_tc_websites()


def backfill_tc_websites():
    """Fill missing accelerator websites from exact TechCrunch company matches."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (fn.accelerator_id)
                    a.id, a.name, fn.website, fn.company_name
                FROM funding_news fn
                JOIN accelerator_companies a ON a.id = fn.accelerator_id
                WHERE fn.source = 'techcrunch'
                  AND fn.website IS NOT NULL
                  AND a.website IS NULL
                ORDER BY fn.accelerator_id, fn.published_at DESC
            """)
            candidates = cur.fetchall()
            rows = []
            for accelerator_id, accelerator_name, website, tc_name in candidates:
                if normalize(accelerator_name) != normalize(tc_name):
                    continue
                cur.execute(
                    """
                    UPDATE accelerator_companies
                    SET website = %s, updated_at = NOW()
                    WHERE id = %s AND website IS NULL
                    RETURNING name
                    """,
                    (website, accelerator_id),
                )
                if cur.fetchone():
                    rows.append((accelerator_name, website, tc_name))
        conn.commit()
        if rows:
            print(f"\nPropagated {len(rows)} TC website(s) to accelerator_companies:")
            for acc_name, new_url, tc_name in rows:
                print(f"  {acc_name} (TC: {tc_name}) → {new_url}")
    finally:
        conn.close()


def backfill_missing_websites():
    """Re-fetch TC articles that have no website and try to extract one.

    Useful after parser improvements to pick up previously missed homepage links.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, article_url FROM funding_news
                WHERE source = 'techcrunch' AND website IS NULL
                ORDER BY published_at DESC
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    print(f"Re-fetching {len(rows)} TC articles with missing website...")
    updated = 0

    for fn_id, url in rows:
        slug = _slug_from_url(url)
        if not slug:
            continue
        try:
            resp = requests.get(
                WP_API,
                params={"slug": slug, "_fields": "content"},
                headers=HEADERS,
                timeout=20,
            )
            time.sleep(SLEEP)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not data:
                continue
            content_html = (data[0] if isinstance(data, list) else data).get("content", {}).get("rendered", "")
            _, website = parse_company_link(content_html)
            if website:
                conn = get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE funding_news SET website = %s WHERE id = %s", (website, fn_id))
                    conn.commit()
                finally:
                    conn.close()
                print(f"  {fn_id}: {website}")
                updated += 1
        except Exception as e:
            print(f"  ERROR {url}: {e}")

    print(f"Done. Updated {updated} rows.")
    if updated:
        backfill_tc_websites()


def _slug_from_url(url: str) -> str | None:
    """Extract the TC post slug from a URL like .../2026/04/02/some-slug/"""
    m = re.search(r"/(\d{4}/\d{2}/\d{2}/)?([^/?#]+?)/?$", url)
    return m.group(2) if m else None


def backfill_round_types():
    """Re-fetch TechCrunch articles that have no round_type and try to extract it from body."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, article_url, article_title FROM funding_news
                WHERE round_type IS NULL AND source = 'techcrunch'
                ORDER BY published_at DESC
            """)
            rows = cur.fetchall()

        print(f"Backfilling round_type for {len(rows)} TC articles...")
        updated = 0

        for fn_id, url, title in rows:
            slug = _slug_from_url(url)
            if not slug:
                continue
            try:
                resp = requests.get(
                    WP_API,
                    params={"slug": slug, "_fields": "content"},
                    headers=HEADERS,
                    timeout=20,
                )
                time.sleep(SLEEP)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if not data:
                    continue
                post = data[0] if isinstance(data, list) else data
                content_html = post.get("content", {}).get("rendered", "")
                body_text = strip_tags(content_html[:1500])
                # Body round labels are accepted only when adjacent to a dollar amount.
                round_type = parse_round(html.unescape(title))
                if not round_type:
                    rm = ROUND_RE.search(body_text)
                    am = AMOUNT_RE.search(body_text)
                    if rm and am and abs(rm.start() - am.start()) <= 150:
                        r = rm.group(1).lower()
                        if "pre" in r:
                            round_type = "Pre-Seed"
                        elif r == "seed":
                            round_type = "Seed"
                        else:
                            round_type = f"Series {r[-1].upper()}"
                if round_type:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE funding_news SET round_type = %s WHERE id = %s",
                            (round_type, fn_id),
                        )
                    conn.commit()
                    print(f"  {round_type:<12}  {title[:60]}")
                    updated += 1
            except Exception as e:
                print(f"  ERROR {url}: {e}")

    finally:
        conn.close()

    print(f"\nBackfill done. Updated {updated} rows.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--backfill", action="store_true", help="Backfill round_type from article bodies")
    parser.add_argument("--backfill-websites", action="store_true",
                        help="Update accelerator_companies.website from TC-sourced URLs")
    parser.add_argument("--backfill-missing", action="store_true",
                        help="Re-fetch TC articles with no website and extract URLs")
    args = parser.parse_args()
    if args.backfill:
        backfill_round_types()
    elif args.backfill_websites:
        backfill_tc_websites()
    elif args.backfill_missing:
        backfill_missing_websites()
    else:
        scrape(days_back=args.days)
