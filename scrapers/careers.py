"""
Careers scraper for EDGAR-matched companies.

For each company matched in edgar_filings, tries Greenhouse → Lever → Ashby →
Workable → BambooHR to find open job listings. Categorizes roles into
Engineering / Product / GTM / Other and stores results in job_listings.
Companies with no ATS found are marked 'not_found'.

Usage:
    uv run python scrapers/careers.py [--limit N]
"""

import re
import sys
import time
from urllib.parse import urlparse

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

HEADERS = {"User-Agent": "startup-recruiting-tool contact@example.com"}
SLEEP = 0.3

# --- Role categorization ---

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
    if ENGINEERING.search(title):
        return "engineering"
    if PRODUCT.search(title):
        return "product"
    if GTM.search(title):
        return "gtm"
    return "other"


# --- Slug derivation ---

def derive_slugs(name: str, website: str | None) -> list[str]:
    slugs = []

    if website:
        try:
            host = urlparse(website if "://" in website else f"https://{website}").netloc
            host = host.lower().lstrip("www.")
            stem = host.split(".")[0]
            if stem:
                slugs.append(stem)
            # for two-part domains like socket.security → socket-security
            parts = host.rsplit(".", 1)[0]
            if "-" not in parts and "." in parts:
                slugs.append(parts.replace(".", "-"))
        except Exception:
            pass

    # normalized company name → slug
    norm = re.sub(r"[^\w\s-]", "", name.lower())
    norm = re.sub(r"\s+", "-", norm.strip())
    # strip legal suffixes
    norm = re.sub(
        r"-(inc|llc|corp|ltd|co|incorporated|limited|company|technologies|software|labs|group|holdings)$",
        "", norm,
    )
    if norm and norm not in slugs:
        slugs.append(norm)

    # no-hyphen variant
    nohyphen = norm.replace("-", "")
    if nohyphen and nohyphen not in slugs:
        slugs.append(nohyphen)

    return [s for s in slugs if s]


# --- ATS fetchers ---

def try_greenhouse(slug: str) -> tuple[list[dict], str] | None:
    url = f"https://boards.greenhouse.io/{slug}/jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
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
            })
        return results, url
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
            results.append({
                "job_id": j.get("id", ""),
                "title": j.get("text", ""),
                "department": j.get("categories", {}).get("department", ""),
                "location": j.get("categories", {}).get("location", ""),
                "job_url": j.get("hostedUrl", ""),
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
    jobPostings { id title locationName teamId }
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
            })
        return results, board_url
    except Exception:
        return None


def try_ashby(slug: str) -> tuple[list[dict], str] | None:
    try:
        r = requests.post(
            ASHBY_GRAPHQL,
            json={"operationName": "ApiJobBoardWithTeams", "variables": {"organizationHostedJobsPageName": slug}, "query": ASHBY_QUERY},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=10,
        )
        time.sleep(SLEEP)
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
            })
        return results, ats_url
    except Exception:
        return None


# --- DB helpers ---

def get_matched_companies(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT a.id, a.name, a.website
            FROM accelerator_companies a
            JOIN edgar_filings e ON e.accelerator_id = a.id
            WHERE a.is_excluded = FALSE
              AND (e.amount_raised IS NULL OR e.amount_raised <= 100000000)
            ORDER BY a.id
        """)
        return [{"id": r[0], "name": r[1], "website": r[2]} for r in cur.fetchall()]


def clear_jobs(conn, company_id: int):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM job_listings WHERE company_id = %s", (company_id,))


def insert_jobs(conn, company_id: int, ats: str, jobs: list[dict]):
    sql = """
        INSERT INTO job_listings
            (company_id, ats, job_id, title, department, location, category, job_url)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (company_id, ats, job_id) DO NOTHING
    """
    with conn.cursor() as cur:
        for j in jobs:
            cat = categorize(j["title"])
            cur.execute(sql, (
                company_id, ats, j["job_id"], j["title"],
                j["department"], j["location"], cat, j["job_url"],
            ))


def update_careers_status(conn, company_id: int, ats: str, url: str | None):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE accelerator_companies
            SET careers_ats = %s, careers_url = %s, careers_scraped_at = NOW()
            WHERE id = %s
        """, (ats, url, company_id))


# --- Main ---

def scrape(limit: int | None = None):
    conn = get_connection()
    try:
        companies = get_matched_companies(conn)
        if limit:
            companies = companies[:limit]

        print(f"Scraping careers for {len(companies)} EDGAR-matched companies...\n")

        found = not_found = 0

        for i, company in enumerate(companies):
            name = company["name"]
            website = company["website"]
            cid = company["id"]
            slugs = derive_slugs(name, website)

            print(f"[{i+1}/{len(companies)}] {name}", end="")

            matched_ats = None
            matched_jobs = []
            matched_url = None

            for ats_name, try_fn in [
                ("greenhouse", try_greenhouse),
                ("lever", try_lever),
                ("ashby", try_ashby),
                ("workable", try_workable),
                ("bamboohr", try_bamboohr),
            ]:
                for slug in slugs:
                    result = try_fn(slug)
                    if result is not None:
                        jobs, url = result
                        matched_ats = ats_name
                        matched_jobs = jobs
                        matched_url = url
                        break
                if matched_ats:
                    break

            if matched_ats:
                clear_jobs(conn, cid)
                insert_jobs(conn, cid, matched_ats, matched_jobs)
                update_careers_status(conn, cid, matched_ats, matched_url)
                conn.commit()

                cats = {}
                for j in matched_jobs:
                    c = categorize(j["title"])
                    cats[c] = cats.get(c, 0) + 1
                summary = " | ".join(f"{k}:{v}" for k, v in sorted(cats.items()))
                print(f" → {matched_ats} ({len(matched_jobs)} jobs) [{summary}]")
                found += 1
            else:
                update_careers_status(conn, cid, "not_found", None)
                conn.commit()
                print(f" → not found")
                not_found += 1

        print(f"\nDone. Found: {found}, Not found: {not_found}")

    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Only process first N companies")
    args = parser.parse_args()
    scrape(limit=args.limit)
