"""
Product Hunt scraper.

Pulls recent product launches via the PH GraphQL API, filters to products
with >= MIN_VOTES upvotes launched in the last DAYS_BACK days, and upserts
into ph_launches. Cross-references with accelerator_companies by website URL
and fuzzy name match.

Requires PH_API_TOKEN in .env (get one at producthunt.com/v2/oauth/applications).

Usage:
    uv run python scrapers/producthunt.py [--days 90] [--min-votes 50]
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from rapidfuzz import fuzz, process

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

load_dotenv()

PH_API = "https://api.producthunt.com/v2/api/graphql"
MIN_VOTES = 50
DAYS_BACK = 90
SLEEP = 0.5

QUERY = """
query($after: String, $postedAfter: DateTime) {
  posts(order: VOTES, after: $after, first: 50, postedAfter: $postedAfter) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        name
        tagline
        url
        website
        votesCount
        createdAt
        makers {
          name
          username
          twitterUsername
        }
      }
    }
  }
}
"""

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


def normalize_url(url: str) -> str:
    """Strip scheme, www, trailing slash for comparison."""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.netloc.lower().lstrip("www.")
        return host
    except Exception:
        return url.lower().strip("/")


def fetch_launches(token: str, days_back: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    posted_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    launches = []
    cursor = None
    page = 0

    while True:
        page += 1
        payload = {"query": QUERY, "variables": {"after": cursor, "postedAfter": posted_after}}
        try:
            resp = requests.post(PH_API, json=payload, headers=headers, timeout=30)
            time.sleep(SLEEP)
        except Exception as e:
            print(f"  Request error on page {page}: {e}")
            break

        if resp.status_code != 200:
            print(f"  API error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        if "errors" in data:
            print(f"  GraphQL errors: {data['errors']}")
            break

        posts = data.get("data", {}).get("posts", {})
        edges = posts.get("edges", [])
        page_info = posts.get("pageInfo", {})

        for edge in edges:
            node = edge.get("node", {})
            votes = node.get("votesCount", 0)
            if votes < MIN_VOTES:
                continue

            makers = node.get("makers", [])
            maker = makers[0] if makers else {}

            raw_website = node.get("website", "") or ""
            # PH wraps external links in redirect URLs — discard them
            website = None if "producthunt.com" in raw_website else raw_website or None

            launches.append({
                "ph_id": str(node["id"]),
                "product_name": node.get("name", ""),
                "tagline": node.get("tagline", ""),
                "ph_url": node.get("url", ""),
                "website": website,
                "votes_count": votes,
                "launched_at": node.get("createdAt"),
                "maker_name": maker.get("name", ""),
                "maker_twitter": maker.get("twitterUsername", ""),
            })

        print(f"  Page {page}: fetched {len(edges)} posts, kept {len(launches)} total (>={MIN_VOTES} votes)")

        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return launches


def load_accelerator_index(conn) -> tuple[list, list, list]:
    """Returns (ids, websites_normalized, names_normalized) for cross-referencing."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, website FROM accelerator_companies")
        rows = cur.fetchall()
    ids = [r[0] for r in rows]
    websites = [normalize_url(r[2] or "") for r in rows]
    names = [normalize(r[1]) for r in rows]
    return ids, websites, names


def find_accelerator_match(launch: dict, ids, websites, names) -> int | None:
    """Match by product name against company name at a high threshold.
    Website matching is unreliable — PH wraps external links in redirect URLs."""
    norm_name = normalize(launch["product_name"])
    if not norm_name:
        return None
    result = process.extractOne(norm_name, names, scorer=fuzz.token_sort_ratio, score_cutoff=97)
    if result:
        _, _, idx = result
        return ids[idx]
    return None


def upsert_launch(conn, launch: dict) -> bool:
    sql = """
        INSERT INTO ph_launches
            (ph_id, product_name, tagline, ph_url, website, votes_count,
             launched_at, maker_name, maker_twitter, accelerator_id)
        VALUES
            (%(ph_id)s, %(product_name)s, %(tagline)s, %(ph_url)s, %(website)s,
             %(votes_count)s, %(launched_at)s, %(maker_name)s, %(maker_twitter)s,
             %(accelerator_id)s)
        ON CONFLICT (ph_id) DO UPDATE SET
            votes_count = EXCLUDED.votes_count,
            accelerator_id = COALESCE(ph_launches.accelerator_id, EXCLUDED.accelerator_id)
        RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        cur.execute(sql, launch)
        row = cur.fetchone()
        return row[0] if row else False


def scrape(days_back: int = DAYS_BACK, min_votes: int = MIN_VOTES):
    token = os.getenv("PH_API_TOKEN")
    if not token:
        print("ERROR: PH_API_TOKEN not set in .env")
        print("Get a token at: producthunt.com/v2/oauth/applications")
        sys.exit(1)

    print(f"Fetching PH launches from last {days_back} days (min votes: {min_votes})...")
    launches = fetch_launches(token, days_back)
    print(f"\nFetched {len(launches)} launches. Cross-referencing with accelerator DB...")

    conn = get_connection()
    try:
        ids, websites, names = load_accelerator_index(conn)

        inserted = updated = matched = 0
        for launch in launches:
            acc_id = find_accelerator_match(launch, ids, websites, names)
            launch["accelerator_id"] = acc_id
            if acc_id:
                matched += 1

            is_new = upsert_launch(conn, launch)
            if is_new:
                inserted += 1
            else:
                updated += 1

            tag = f" [ACC MATCH]" if acc_id else ""
            print(f"  {'NEW' if is_new else 'UPD'} {launch['votes_count']:4d}v  {launch['product_name'][:40]}{tag}")

        conn.commit()
    finally:
        conn.close()

    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Matched to accelerator: {matched}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DAYS_BACK)
    parser.add_argument("--min-votes", type=int, default=MIN_VOTES)
    args = parser.parse_args()

    scrape(days_back=args.days, min_votes=args.min_votes)
