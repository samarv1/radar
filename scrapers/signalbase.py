"""
Signalbase funding news scraper.

Fetches recently funded startup pages from trysignalbase.com via their public
sitemap, parses company name/amount/round from JSON-LD + meta tags, and upserts
into funding_news with source='signalbase'.

Usage:
    uv run python scrapers/signalbase.py [--days 7]
"""

import html as html_lib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

import requests
from rapidfuzz import fuzz, process

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

SITEMAP_BASE = "https://www.trysignalbase.com/sitemap/{}"
SITEMAP_COUNT = 7
HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}
SLEEP = 0.2   # per-worker sleep; with DEFAULT_WORKERS=10 this is ~2 req/s per worker
DEFAULT_WORKERS = 10

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Title verbs used to split "Company Name Raises $X"
TITLE_SPLIT_RE = re.compile(
    r"\s+(?:raises?|closes?|secures?|lands?|gets?|wins?|announces?|receives?|completes?|"
    r"nets?|bags?|attracts?|earns?|obtains?|clinches?)\b",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(
    r"\$(\d+(?:\.\d+)?)\s*(billion|million|[BMK])\b",
    re.IGNORECASE,
)

# Also handle bare "$9.4M" without a unit word when unit is the letter suffix
AMOUNT_SUFFIX_RE = re.compile(
    r"\$(\d+(?:\.\d+)?)([BMK])\b",
    re.IGNORECASE,
)

ROUND_RE = re.compile(
    r"\b(pre-?seed|seed|series [a-e]|series-[a-e])\b",
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


def normalize(name: str) -> str:
    name = name.lower()
    name = PUNCTUATION.sub(" ", name)
    name = LEGAL_SUFFIXES.sub(" ", name)
    name = WHITESPACE.sub(" ", name).strip()
    return name


def parse_amount(text: str) -> float | None:
    m = AMOUNT_RE.search(text) or AMOUNT_SUFFIX_RE.search(text)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).upper()
    if unit in ("BILLION", "B"):
        value *= 1_000_000_000
    elif unit in ("MILLION", "M"):
        value *= 1_000_000
    elif unit == "K":
        value *= 1_000
    return value


def parse_round(text: str) -> str | None:
    m = ROUND_RE.search(text)
    if not m:
        return None
    r = m.group(1).lower().replace("-", "")
    if "preseed" in r:
        return "Pre-Seed"
    if r == "seed":
        return "Seed"
    # "series a" → "Series A"
    letter = r[-1].upper()
    return f"Series {letter}"


def parse_company_from_title(title: str) -> str | None:
    """Extract company name from 'Company Name Raises $X' pattern."""
    parts = TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) < 2:
        return None
    name = parts[0].strip().strip("'\"").strip()
    # Drop trailing parentheticals like "(YC W24)"
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if not name or len(name) > 80:
        return None
    return name


def fetch_sitemap_urls(days_back: int) -> list[str]:
    """Return funding page URLs whose lastmod is within days_back days."""
    cutoff = date.today() - timedelta(days=days_back)
    funding_urls = []

    for i in range(SITEMAP_COUNT):
        url = SITEMAP_BASE.format(i)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            time.sleep(0.3)
            if resp.status_code != 200:
                print(f"  sitemap/{i}: HTTP {resp.status_code}, skipping")
                continue
        except Exception as e:
            print(f"  sitemap/{i}: error {e}, skipping")
            continue

        root = ET.fromstring(resp.text)
        entries = root.findall(f"{{{SITEMAP_NS}}}url")

        oldest_in_sitemap = None
        count_before = len(funding_urls)

        for entry in entries:
            loc_el = entry.find(f"{{{SITEMAP_NS}}}loc")
            lastmod_el = entry.find(f"{{{SITEMAP_NS}}}lastmod")
            if loc_el is None:
                continue

            loc = loc_el.text or ""
            if "/news/funding/" not in loc:
                continue

            if lastmod_el is not None and lastmod_el.text:
                try:
                    lastmod = date.fromisoformat(lastmod_el.text[:10])
                except ValueError:
                    lastmod = None
            else:
                lastmod = None

            if lastmod is not None:
                if oldest_in_sitemap is None or lastmod < oldest_in_sitemap:
                    oldest_in_sitemap = lastmod
                if lastmod < cutoff:
                    continue

            funding_urls.append(loc)

        added = len(funding_urls) - count_before
        print(f"  sitemap/{i}: {added} funding URLs in window (oldest lastmod: {oldest_in_sitemap})")

        # If all entries in this sitemap are older than our cutoff, no need to continue
        if oldest_in_sitemap is not None and oldest_in_sitemap < cutoff:
            break

    return funding_urls


def fetch_page(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        time.sleep(SLEEP)
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


_INDUSTRY_BADGE_RE = re.compile(
    r'<span class="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600">([^<]+)</span>'
)

_SKIP_DOMAINS = re.compile(
    r"(trysignalbase|images\.|docs\.|linkedin|twitter|x\.com|kvk\.nl|"
    r"bloomberg|crunchbase|techcrunch|uktech\.news|facebook|instagram|youtube)",
    re.IGNORECASE,
)

# Signalbase embeds company website as a UTM-tagged link: href="https://company.com/?utm_source=trysignalbase..."
_UTM_LINK_RE = re.compile(
    r'href="(https?://[^"]+utm_source=trysignalbase[^"]*)"',
    re.IGNORECASE,
)


def _strip_tracking(url: str) -> str:
    """Return just scheme+host+/ with all query params removed."""
    url = html_lib.unescape(url)
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, "/", "", "", ""))


def parse_company_website(html: str) -> str | None:
    """Extract the company's own website from a Signalbase funding page.

    Signalbase embeds the company website as a UTM-tagged anchor:
      href="https://company.com/?utm_source=trysignalbase.com&utm_medium=referral"
    We take the first such link that doesn't belong to a known media/platform domain.
    """
    for m in _UTM_LINK_RE.finditer(html):
        raw = m.group(1)
        domain = urlparse(html_lib.unescape(raw)).netloc
        if not _SKIP_DOMAINS.search(domain):
            return _strip_tracking(raw)
    return None


def parse_page(html: str, url: str) -> dict | None:
    """Extract funding data from a Signalbase page via JSON-LD and meta tags."""
    # JSON-LD is the cleanest source — prefer it
    ld_data = {}
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            if obj.get("@type") == "NewsArticle":
                ld_data = obj
                break
        except (json.JSONDecodeError, AttributeError):
            continue

    # og:title: "Company Name Raises $X | Signalbase" or just "Company Name Raises $X"
    og_title_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    og_title = html_lib.unescape(og_title_m.group(1)) if og_title_m else ""
    # Strip " | Signalbase" suffix if present
    og_title = re.sub(r"\s*\|\s*Signalbase\s*$", "", og_title, flags=re.IGNORECASE).strip()

    # description (og:description or name="description")
    desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
    description = html_lib.unescape(desc_m.group(1)) if desc_m else ""

    # published_at from JSON-LD or article:published_time meta
    published_str = ld_data.get("datePublished") or ""
    if not published_str:
        pub_m = re.search(r'<meta property="article:published_time" content="([^"]+)"', html)
        published_str = pub_m.group(1) if pub_m else ""

    if not published_str:
        return None

    try:
        published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
    except ValueError:
        return None

    # Title is most reliable source for company name and amount
    title = og_title or ld_data.get("headline", "")
    if not title:
        return None

    article_title = title

    company = parse_company_from_title(title)
    if not company:
        return None

    amount = parse_amount(title)
    # Exclude micro-grants/noise (< $50K) and growth-stage raises (> $100M per spec)
    if amount is not None and (amount < 50_000 or amount > 100_000_000):
        return None

    # Round type: check title first, then description (description often has full text)
    round_type = parse_round(title) or parse_round(description)
    website = parse_company_website(html)

    industry_m = _INDUSTRY_BADGE_RE.search(html)
    industry = html_lib.unescape(industry_m.group(1)).strip() if industry_m else None

    return {
        "company_name": company,
        "amount_usd": amount,
        "round_type": round_type,
        "article_title": article_title,
        "article_url": url,
        "published_at": published_at.isoformat(),
        "website": website,
        "industry": industry,
    }


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
             published_at, source, accelerator_id, website, industry)
        VALUES
            (%(company_name)s, %(amount_usd)s, %(round_type)s, %(article_title)s,
             %(article_url)s, %(published_at)s, 'signalbase', %(accelerator_id)s, %(website)s,
             %(industry)s)
        ON CONFLICT (article_url) DO UPDATE SET
            accelerator_id = COALESCE(funding_news.accelerator_id, EXCLUDED.accelerator_id),
            company_name = EXCLUDED.company_name,
            round_type = COALESCE(funding_news.round_type, EXCLUDED.round_type),
            amount_usd = COALESCE(funding_news.amount_usd, EXCLUDED.amount_usd),
            website = COALESCE(funding_news.website, EXCLUDED.website),
            industry = COALESCE(funding_news.industry, EXCLUDED.industry)
        RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
        result = cur.fetchone()
        return result[0] if result else False


def _fetch_and_parse(url: str) -> dict | None:
    """Fetch a single page and parse it. Runs in a worker thread."""
    html = fetch_page(url)
    if not html:
        return None
    return parse_page(html, url)


def scrape(days_back: int = 2, workers: int = DEFAULT_WORKERS):
    print(f"Fetching Signalbase funding URLs (last {days_back} days)...")
    urls = fetch_sitemap_urls(days_back)
    print(f"Found {len(urls)} funding URLs to process (workers={workers})")

    if not urls:
        print("No URLs in window.")
        return

    conn = get_connection()
    try:
        ids, names_norm = load_accelerator_index(conn)
        inserted = updated = skipped = matched = 0
        done = 0

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_and_parse, url): url for url in urls}
            for future in as_completed(futures):
                done += 1
                row = future.result()
                if not row:
                    skipped += 1
                    continue

                acc_id = find_match(row["company_name"], ids, names_norm)
                if acc_id:
                    matched += 1
                row["accelerator_id"] = acc_id

                is_new = upsert(conn, row)
                tag = " [ACC MATCH]" if acc_id else ""
                amt = row["amount_usd"]
                amount_str = f"${amt/1e6:.1f}M" if amt and amt >= 1e6 else (f"${amt/1e3:.0f}K" if amt else "?")
                print(
                    f"  [{done}/{len(urls)}] {'NEW' if is_new else 'UPD'}  "
                    f"{row['company_name'][:35]:<35}  {row['round_type'] or '?':<10}  {amount_str:>8}{tag}"
                )
                if is_new:
                    inserted += 1
                else:
                    updated += 1

                # Commit every 100 rows so progress isn't lost if interrupted
                if done % 100 == 0:
                    conn.commit()

        conn.commit()
    finally:
        conn.close()

    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Skipped: {skipped}, Matched to accelerator: {matched}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    scrape(days_back=args.days)
