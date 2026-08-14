"""
Per-ATS job-board fetchers.

Each `try_<ats>(slug)` hits that ATS's public API/board and returns
`(jobs, board_url)` on success or `None` on any failure (unknown slug,
non-200, unexpected shape) so callers can fall through to the next ATS.
"""

import threading
import time

import requests

from scrapers._common import DEFAULT_HEADERS

HEADERS = DEFAULT_HEADERS
SLEEP = 0.3

REAL_ATS = frozenset({"greenhouse", "lever", "ashby", "workable", "bamboohr"})

_ashby_semaphore = threading.Semaphore(3)  # max 3 concurrent Ashby calls

ASHBY_GRAPHQL = "https://app.ashbyhq.com/api/non-user-graphql"
ASHBY_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    teams { id name }
    jobPostings { id title locationName teamId publishedAt }
  }
}
"""


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


ATS_FETCHERS = {
    "greenhouse": try_greenhouse,
    "lever": try_lever,
    "ashby": try_ashby,
    "workable": try_workable,
    "bamboohr": try_bamboohr,
}
