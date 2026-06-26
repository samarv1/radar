"""
Careers scraper.

Default mode: scrapes companies that have an EDGAR filing ≤ $100M (daily pipeline).
Hiring sweep mode (--hiring-sweep): scrapes ALL non-excluded accelerator companies
regardless of EDGAR status — used weekly to populate the Hiring section.

Tries Greenhouse → Lever → Ashby → Workable → BambooHR for each company.
Categorizes roles into Engineering / Product / GTM / Other.

Usage:
    uv run python scrapers/careers.py [--limit N] [--hiring-sweep]
"""

import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

_print_lock = threading.Lock()
_ashby_semaphore = threading.Semaphore(3)  # max 3 concurrent Ashby calls

HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}
SLEEP = 0.3

# --- Role categorization ---

INTERN = re.compile(
    r"\b(intern|internship|co-?op|apprentice|apprenticeship)\b",
    re.IGNORECASE,
)

NEW_GRAD = re.compile(
    r"\b(new.?grad|new graduate|recent grad|recent graduate|entry.?level|"
    r"university grad|campus hire|junior|associate engineer|associate software|"
    r"associate developer|associate data|associate product)\b",
    re.IGNORECASE,
)

ENGINEERING = re.compile(
    r"\b(engineer|engineering|developer|software|backend|front.?end|full.?stack|"
    r"data|ml|machine learning|ai|artificial intelligence|infrastructure|devops|"
    r"sre|site reliability|platform|security|qa|quality|hardware|embedded|firmware|"
    r"scientist|research scientist|applied|cloud|mobile|ios|android|systems)\b",
    re.IGNORECASE,
)

PRODUCT = re.compile(
    r"\b(product manager|product lead|pm\b|principal pm|"
    r"product designer|ux|ui\b|user experience|user research|"
    r"designer|design|researcher|research)\b",
    re.IGNORECASE,
)

GTM = re.compile(
    r"\b(sales|account executive|ae\b|sdr|bdr|business development|"
    r"marketing|growth|revenue|customer success|cs\b|customer support|"
    r"partnerships|partner|solutions engineer|solutions consultant|"
    r"demand generation|field|go.?to.?market|gtm|brand|content|"
    r"communications|pr\b|public relations|social media|community)\b",
    re.IGNORECASE,
)


def categorize(title: str) -> str:
    if INTERN.search(title):
        return "intern"
    if NEW_GRAD.search(title):
        return "new_grad"
    if ENGINEERING.search(title):
        return "engineering"
    if PRODUCT.search(title):
        return "product"
    if GTM.search(title):
        return "gtm"
    return "other"


# --- ATS discovery (website-first) ---

# Patterns to detect ATS systems in redirect URLs and page HTML
_ATS_PATTERNS = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/([^/?\s\"']+)", re.I)),
    ("lever",      re.compile(r"jobs\.lever\.co/([^/?\s\"']+)", re.I)),
    ("ashby",      re.compile(r"jobs\.ashbyhq\.com/([^/?\s\"']+)", re.I)),
    ("workable",   re.compile(r"apply\.workable\.com/([^/?\s\"']+)", re.I)),
    ("bamboohr",   re.compile(r"([\w-]+)\.bamboohr\.com", re.I)),
]

_CAREERS_PATHS = [
    "/careers", "/jobs", "/join", "/about/careers",
    "/work-with-us", "/open-roles", "/about/jobs", "/company/careers",
]

_MEDIA_NETLOCS = {
    "bloomberg.com", "wsj.com", "reuters.com", "forbes.com", "nytimes.com",
    "prnewswire.com", "businesswire.com", "crunchbase.com", "pitchbook.com",
    "linkedin.com", "twitter.com", "x.com", "youtube.com", "facebook.com",
    "instagram.com", "wikipedia.org", "sec.gov", "techcrunch.com",
    "apnews.com", "cnbc.com", "wired.com", "theinformation.com",
    "venturebeat.com", "axios.com", "sifted.eu",
    "apps.apple.com", "itunes.apple.com", "play.google.com",
    "producthunt.com", "ycombinator.com",
}


def _is_media_domain(url: str) -> bool:
    """Return True if the URL's domain is a known media/social/platform site."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc in _MEDIA_NETLOCS
    except Exception:
        return False


def _is_likely_homepage(url: str) -> bool:
    """Return True only if the URL looks like a company root domain, not an article or subpage."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        # More than 1 path segment suggests an article/deep subpage, not a homepage
        segments = [s for s in parsed.path.rstrip("/").split("/") if s]
        return len(segments) <= 1
    except Exception:
        return False


def _board_url(ats: str, slug: str) -> str:
    if ats == "greenhouse":
        return f"https://boards.greenhouse.io/{slug}"
    if ats == "lever":
        return f"https://jobs.lever.co/{slug}"
    if ats == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    if ats == "workable":
        return f"https://apply.workable.com/{slug}"
    if ats == "bamboohr":
        return f"https://{slug}.bamboohr.com/careers"
    return ""


def discover_ats(website: str) -> tuple[str, str, str] | None:
    """Return (ats_name, slug, board_url) by following links from company's own website.

    Tries common careers paths, follows redirects, then scans the final URL and
    page HTML for known ATS domain patterns. No slug guessing — the slug comes
    directly from the company's own redirect chain or embedded link.
    """
    base = website.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    for path in _CAREERS_PATHS:
        try:
            r = requests.get(base + path, headers=HEADERS, timeout=10, allow_redirects=True)
            time.sleep(SLEEP)
            # Check final URL after redirects
            for ats, pattern in _ATS_PATTERNS:
                m = pattern.search(r.url)
                if m:
                    slug = m.group(1).strip("/")
                    return ats, slug, _board_url(ats, slug)
            # Scan page body for embedded ATS links
            if r.status_code == 200 and len(r.content) < 2_000_000:
                for ats, pattern in _ATS_PATTERNS:
                    m = pattern.search(r.text)
                    if m:
                        slug = m.group(1).strip("/")
                        return ats, slug, _board_url(ats, slug)
        except Exception:
            pass
    return None


# --- ATS fetchers ---

def try_greenhouse(slug: str) -> tuple[list[dict], str] | None:
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    board_url = f"https://boards.greenhouse.io/{slug}"
    try:
        r = requests.get(api_url, headers=HEADERS, timeout=10)
        time.sleep(SLEEP)
        if r.status_code != 200:
            return None
        data = r.json()
        jobs = data.get("jobs", [])
        if not isinstance(jobs, list):
            return None
        results = []
        for j in jobs:
            results.append({
                "job_id": str(j.get("id", "")),
                "title": j.get("title", ""),
                "department": (j.get("departments") or [{}])[0].get("name", "") if j.get("departments") else "",
                "location": (j.get("offices") or [{}])[0].get("name", "") if j.get("offices") else "",
                "job_url": j.get("absolute_url", ""),
                "posted_at": j.get("updated_at"),
            })
        return results, board_url
    except Exception:
        return None


def try_lever(slug: str) -> tuple[list[dict], str] | None:
    api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    board_url = f"https://jobs.lever.co/{slug}"
    try:
        r = requests.get(api_url, headers=HEADERS, timeout=10)
        time.sleep(SLEEP)
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, list):
            return None
        results = []
        for j in data:
            created_ms = j.get("createdAt")
            posted_at = None
            if created_ms:
                from datetime import datetime, timezone
                posted_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
            results.append({
                "job_id": j.get("id", ""),
                "title": j.get("text", ""),
                "department": j.get("categories", {}).get("department", ""),
                "location": j.get("categories", {}).get("location", ""),
                "job_url": j.get("hostedUrl", ""),
                "posted_at": posted_at,
            })
        if not results:
            return None
        return results, board_url
    except Exception:
        return None


ASHBY_GRAPHQL = "https://app.ashbyhq.com/api/non-user-graphql"
ASHBY_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    teams { id name }
    jobPostings { id title locationName teamId publishedAt }
  }
}
"""


def try_workable(slug: str) -> tuple[list[dict], str] | None:
    url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    board_url = f"https://apply.workable.com/{slug}"
    try:
        r = requests.post(
            url,
            json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=10,
        )
        time.sleep(SLEEP)
        if r.status_code != 200:
            return None
        data = r.json()
        jobs_raw = data.get("results", [])
        if not isinstance(jobs_raw, list) or not jobs_raw:
            return None
        results = []
        for j in jobs_raw:
            results.append({
                "job_id": j.get("shortcode", j.get("id", "")),
                "title": j.get("title", ""),
                "department": j.get("department", ""),
                "location": (j.get("location") or {}).get("city", ""),
                "job_url": f"{board_url}/j/{j.get('shortcode', '')}",
                "posted_at": j.get("created"),
            })
        return results, board_url
    except Exception:
        return None


def try_bamboohr(slug: str) -> tuple[list[dict], str] | None:
    board_url = f"https://{slug}.bamboohr.com/careers"
    url = f"https://{slug}.bamboohr.com/careers/list"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        time.sleep(SLEEP)
        if r.status_code != 200:
            return None
        data = r.json()
        jobs_raw = data.get("result", [])
        if not isinstance(jobs_raw, list) or not jobs_raw:
            return None
        results = []
        for j in jobs_raw:
            jid = str(j.get("id", ""))
            results.append({
                "job_id": jid,
                "title": j.get("title", {}).get("label", "") if isinstance(j.get("title"), dict) else str(j.get("title", "")),
                "department": j.get("department", {}).get("label", "") if isinstance(j.get("department"), dict) else str(j.get("department", "")),
                "location": j.get("location", {}).get("label", "") if isinstance(j.get("location"), dict) else str(j.get("location", "")),
                "job_url": f"{board_url}/{jid}",
                "posted_at": None,
            })
        return results, board_url
    except Exception:
        return None


def try_ashby(slug: str) -> tuple[list[dict], str] | None:
    with _ashby_semaphore:
        try:
            for attempt in range(3):
                r = requests.post(
                    ASHBY_GRAPHQL,
                    json={"operationName": "ApiJobBoardWithTeams", "variables": {"organizationHostedJobsPageName": slug}, "query": ASHBY_QUERY},
                    headers={**HEADERS, "Content-Type": "application/json"},
                    timeout=10,
                )
                time.sleep(SLEEP)
                if r.status_code == 429:
                    time.sleep(10 * (3 ** attempt))  # 10s, 30s, 90s
                    continue
                break
            if r.status_code != 200:
                return None
            data = r.json()
            if "errors" in data:
                return None
            jb = data.get("data", {}).get("jobBoardWithTeams")
            if not jb:
                return None
            teams = {t["id"]: t["name"] for t in jb.get("teams", [])}
            jobs_raw = jb.get("jobPostings", [])
            if not isinstance(jobs_raw, list):
                return None
            ats_url = f"https://jobs.ashbyhq.com/{slug}"
            results = []
            for j in jobs_raw:
                results.append({
                    "job_id": j.get("id", ""),
                    "title": j.get("title", ""),
                    "department": teams.get(j.get("teamId", ""), ""),
                    "location": j.get("locationName", ""),
                    "job_url": f"{ats_url}/{j.get('id', '')}",
                    "posted_at": j.get("publishedAt"),
                })
            return results, ats_url
        except Exception:
            return None


# --- DB helpers ---

def get_pending_companies(
    conn,
    rescrape_after_days: int | None = None,
    hiring_sweep: bool = False,
) -> list[dict]:
    staleness = (
        f"OR a.careers_scraped_at < NOW() - INTERVAL '{rescrape_after_days} days'"
        if rescrape_after_days is not None
        else ""
    )
    if hiring_sweep:
        # Sweep accelerator companies regardless of EDGAR status.
        # Exclude companies with known large raises (>$100M EDGAR filing).
        # Per-accelerator strategy:
        #   YC/Techstars  — all (no batch filter; $100M check handles large exits)
        #   a16z          — exclude stage containing 'Growth' or 'EXIT'
        #   Sequoia       — only Pre-Seed/Seed or Early stage
        #   Pear/Lightspeed — include all
        sql = f"""
            SELECT DISTINCT a.id, a.name, a.website
            FROM accelerator_companies a
            WHERE a.is_excluded = FALSE
              AND (a.careers_scraped_at IS NULL {staleness})
              AND NOT EXISTS (
                SELECT 1 FROM edgar_filings ef
                WHERE ef.accelerator_id = a.id
                  AND ef.amount_raised > 100000000
              )
              AND (
                a.accelerator IN ('yc', 'techstars')
                OR (a.accelerator = 'a16z'
                    AND (a.stage IS NULL
                         OR (a.stage NOT ILIKE '%growth%' AND a.stage NOT ILIKE '%exit%')))
                OR (a.accelerator = 'sequoia'
                    AND (a.stage IS NULL OR a.stage IN ('Pre-Seed/Seed', 'Early')))
                OR a.accelerator IN ('pear', 'lightspeed')
              )
            ORDER BY a.id
        """
    else:
        sql = f"""
            SELECT DISTINCT a.id, a.name, a.website
            FROM accelerator_companies a
            JOIN edgar_filings e ON e.accelerator_id = a.id
            WHERE a.is_excluded = FALSE
              AND (e.amount_raised IS NULL OR e.amount_raised <= 100000000)
              AND (a.careers_scraped_at IS NULL {staleness})
            ORDER BY a.id
        """
    with conn.cursor() as cur:
        cur.execute(sql)
        return [{"id": r[0], "name": r[1], "website": r[2]} for r in cur.fetchall()]


def clear_jobs(conn, company_id: int):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM job_listings WHERE company_id = %s", (company_id,))


def sync_jobs(conn, company_id: int, ats: str, jobs: list[dict]):
    """Diff-based upsert: insert new jobs (preserving first_seen_at), delete removed ones."""
    fresh_ids = {j["job_id"] for j in jobs}

    with conn.cursor() as cur:
        # Get existing job_ids for this company
        cur.execute(
            "SELECT job_id FROM job_listings WHERE company_id = %s AND ats = %s",
            (company_id, ats),
        )
        existing_ids = {row[0] for row in cur.fetchall()}

        # Remove jobs that disappeared from the ATS
        removed = existing_ids - fresh_ids
        if removed:
            cur.execute(
                "DELETE FROM job_listings WHERE company_id = %s AND ats = %s AND job_id = ANY(%s)",
                (company_id, ats, list(removed)),
            )

        # Insert new jobs (first_seen_at = NOW() marks when we first noticed them)
        new_jobs = [j for j in jobs if j["job_id"] not in existing_ids]
        if new_jobs:
            insert_sql = """
                INSERT INTO job_listings
                    (company_id, ats, job_id, title, department, location, category,
                     job_url, posted_at, first_seen_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (company_id, ats, job_id) DO NOTHING
            """
            for j in new_jobs:
                cat = categorize(j["title"])
                cur.execute(insert_sql, (
                    company_id, ats, j["job_id"], j["title"],
                    j["department"], j["location"], cat, j["job_url"],
                    j.get("posted_at"),
                ))

        # Update scraped_at on all remaining (still-active) jobs
        if fresh_ids:
            cur.execute(
                "UPDATE job_listings SET scraped_at = NOW() WHERE company_id = %s AND ats = %s",
                (company_id, ats),
            )


def update_careers_status(conn, company_id: int, ats: str, url: str | None):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE accelerator_companies
            SET careers_ats = %s, careers_url = %s, careers_scraped_at = NOW()
            WHERE id = %s
        """, (ats, url, company_id))


# --- Main ---

_ATS_FETCHERS = {
    "greenhouse": try_greenhouse,
    "lever": try_lever,
    "ashby": try_ashby,
    "workable": try_workable,
    "bamboohr": try_bamboohr,
}


def _scrape_one(company: dict, total: int, idx: int) -> bool:
    """Scrape a single company using its own DB connection. Returns True if found."""
    name = company["name"]
    website = company["website"]
    cid = company["id"]

    matched_ats = None
    matched_jobs = []
    matched_url = None

    # Only trust 'not_found' as a signal when the website looks like an actual company homepage.
    # TC-scraped article URLs or media domains would produce false not_found results.
    valid_website = (
        bool(website)
        and _is_likely_homepage(website)
        and not _is_media_domain(website)
    )

    if valid_website:
        discovery = discover_ats(website)
        if discovery:
            ats_name, slug, board_url = discovery
            fetcher = _ATS_FETCHERS.get(ats_name)
            if fetcher:
                result = fetcher(slug)
                if result is not None:
                    matched_jobs, matched_url = result
                    matched_ats = ats_name
                else:
                    # ATS detected but API returned nothing (board exists, zero jobs)
                    matched_ats = ats_name
                    matched_url = board_url
    elif website:
        with _print_lock:
            print(f"[{idx}/{total}] {name} → skipped bad URL: {website}")

    conn = get_connection()
    try:
        if matched_ats:
            sync_jobs(conn, cid, matched_ats, matched_jobs)
            update_careers_status(conn, cid, matched_ats, matched_url)
            conn.commit()

            cats = {}
            for j in matched_jobs:
                c = categorize(j["title"])
                cats[c] = cats.get(c, 0) + 1
            summary = " | ".join(f"{k}:{v}" for k, v in sorted(cats.items()))
            with _print_lock:
                print(f"[{idx}/{total}] {name} → {matched_ats} ({len(matched_jobs)} jobs) [{summary}]")
            return True
        else:
            clear_jobs(conn, cid)
            # Only mark 'not_found' if we actually checked a valid company website.
            # No website or a bad URL → leave careers_ats as NULL (unknown, not 'not hiring').
            ats_status = "not_found" if valid_website else None
            update_careers_status(conn, cid, ats_status, None)
            conn.commit()
            with _print_lock:
                label = "not found" if valid_website else "no valid website"
                print(f"[{idx}/{total}] {name} → {label}")
            return False
    finally:
        conn.close()


def scrape(
    limit: int | None = None,
    rescrape_after_days: int | None = None,
    hiring_sweep: bool = False,
    workers: int = 1,
):
    conn = get_connection()
    try:
        companies = get_pending_companies(conn, rescrape_after_days, hiring_sweep=hiring_sweep)
    finally:
        conn.close()

    if limit:
        companies = companies[:limit]

    mode = "hiring sweep" if hiring_sweep else "EDGAR-matched"
    print(f"Scraping careers for {len(companies)} companies [{mode}] workers={workers}...\n")

    total = len(companies)
    found = not_found = 0

    if workers <= 1:
        for i, company in enumerate(companies):
            result = _scrape_one(company, total, i + 1)
            if result:
                found += 1
            else:
                not_found += 1
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_scrape_one, company, total, i + 1): company
                for i, company in enumerate(companies)
            }
            for future in as_completed(futures):
                try:
                    if future.result():
                        found += 1
                    else:
                        not_found += 1
                except Exception as e:
                    company = futures[future]
                    with _print_lock:
                        print(f"  ERROR {company['name']}: {e}")
                    not_found += 1

    print(f"\nDone. Found: {found}, Not found: {not_found}")


def fix_bad_websites():
    """Find companies whose website URL looks like an article or media page and clear it.

    Sets website=NULL, careers_ats=NULL, careers_scraped_at=NULL so the company
    gets a fresh honest scrape on the next pipeline run.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, website FROM accelerator_companies
                WHERE website IS NOT NULL AND is_excluded = FALSE
            """)
            rows = cur.fetchall()

        to_clear = [
            (cid, name, url)
            for cid, name, url in rows
            if not _is_likely_homepage(url) or _is_media_domain(url)
        ]

        if not to_clear:
            print("No bad website URLs found.")
            return

        print(f"Found {len(to_clear)} companies with suspicious website URLs:")
        for _, name, url in to_clear:
            print(f"  {name}: {url}")

        with conn.cursor() as cur:
            for cid, _, _ in to_clear:
                cur.execute("""
                    UPDATE accelerator_companies
                    SET website = NULL, careers_ats = NULL, careers_scraped_at = NULL
                    WHERE id = %s
                """, (cid,))
        conn.commit()
        print(f"\nCleared {len(to_clear)} bad website URLs. Re-run the scraper to pick them up fresh.")
    finally:
        conn.close()


def reset_careers_data():
    """Wipe all ATS/careers data so companies get re-scraped with website-first discovery."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM job_listings")
            deleted_jobs = cur.rowcount
            cur.execute("""
                UPDATE accelerator_companies
                SET careers_ats = NULL, careers_url = NULL, careers_scraped_at = NULL
            """)
            reset_companies = cur.rowcount
        conn.commit()
        print(f"Wiped {deleted_jobs} job listings and reset {reset_companies} companies.")
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Only process first N companies")
    parser.add_argument("--hiring-sweep", action="store_true", help="Scrape all accelerator companies regardless of EDGAR status")
    parser.add_argument("--rescrape-after-days", type=int, help="Re-scrape companies last scraped more than N days ago")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers (default: 1)")
    parser.add_argument("--reset-all", action="store_true", help="Wipe all ATS/careers data before re-scraping")
    parser.add_argument("--fix-websites", action="store_true", help="Clear bad website URLs (articles, media pages) so companies get re-scraped honestly")
    args = parser.parse_args()
    if args.reset_all:
        reset_careers_data()
    elif args.fix_websites:
        fix_bad_websites()
    else:
        scrape(limit=args.limit, rescrape_after_days=args.rescrape_after_days, hiring_sweep=args.hiring_sweep, workers=args.workers)
