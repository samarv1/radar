"""Fetch and normalize public job boards for supported ATS providers."""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import requests

from scrapers._common import DEFAULT_HEADERS

HEADERS = DEFAULT_HEADERS
SLEEP = 0.3

REAL_ATS = frozenset({"greenhouse", "lever", "ashby", "workable", "bamboohr"})
FetchStatus = Literal["success", "empty", "not_found", "transient_error"]


@dataclass(frozen=True)
class FetchResult:
    status: FetchStatus
    board_url: str | None = None
    jobs: list[dict] = field(default_factory=list)


_ashby_semaphore = threading.Semaphore(3)

ASHBY_GRAPHQL = "https://app.ashbyhq.com/api/non-user-graphql"
ASHBY_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    teams { id name }
    jobPostings { id title locationName teamId }
  }
}
"""


def _http_failure(status_code: int, board_url: str) -> FetchResult | None:
    if status_code == 200:
        return None
    if status_code == 429 or status_code >= 500:
        return FetchResult("transient_error", board_url)
    return FetchResult("not_found", board_url)


def _jobs_result(jobs: list[dict], board_url: str) -> FetchResult:
    return FetchResult("success" if jobs else "empty", board_url, jobs)


def try_greenhouse(slug: str) -> FetchResult:
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    board_url = f"https://boards.greenhouse.io/{slug}"
    try:
        response = requests.get(api_url, headers=HEADERS, timeout=10)
        time.sleep(SLEEP)
        if failure := _http_failure(response.status_code, board_url):
            return failure
        jobs_raw = response.json().get("jobs", [])
        if not isinstance(jobs_raw, list):
            return FetchResult("transient_error", board_url)
        jobs = [{
            "job_id": str(job.get("id", "")),
            "title": job.get("title", ""),
            "department": (job.get("departments") or [{}])[0].get("name", ""),
            "location": (job.get("offices") or [{}])[0].get("name", ""),
            "job_url": job.get("absolute_url", ""),
            "posted_at": job.get("updated_at"),
        } for job in jobs_raw]
        return _jobs_result(jobs, board_url)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return FetchResult("transient_error", board_url)


def try_lever(slug: str) -> FetchResult:
    api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    board_url = f"https://jobs.lever.co/{slug}"
    try:
        response = requests.get(api_url, headers=HEADERS, timeout=10)
        time.sleep(SLEEP)
        if failure := _http_failure(response.status_code, board_url):
            return failure
        jobs_raw = response.json()
        if not isinstance(jobs_raw, list):
            return FetchResult("transient_error", board_url)
        jobs = []
        for job in jobs_raw:
            created_ms = job.get("createdAt")
            posted_at = None
            if created_ms:
                posted_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
            jobs.append({
                "job_id": job.get("id", ""),
                "title": job.get("text", ""),
                "department": job.get("categories", {}).get("department", ""),
                "location": job.get("categories", {}).get("location", ""),
                "job_url": job.get("hostedUrl", ""),
                "posted_at": posted_at,
            })
        return _jobs_result(jobs, board_url)
    except (requests.RequestException, ValueError, TypeError, AttributeError, OSError):
        return FetchResult("transient_error", board_url)


def try_workable(slug: str) -> FetchResult:
    api_url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    board_url = f"https://apply.workable.com/{slug}"
    try:
        response = requests.post(
            api_url,
            json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=10,
        )
        time.sleep(SLEEP)
        if failure := _http_failure(response.status_code, board_url):
            return failure
        jobs_raw = response.json().get("results", [])
        if not isinstance(jobs_raw, list):
            return FetchResult("transient_error", board_url)
        jobs = [{
            "job_id": job.get("shortcode", job.get("id", "")),
            "title": job.get("title", ""),
            "department": job.get("department", ""),
            "location": (job.get("location") or {}).get("city", ""),
            "job_url": f"{board_url}/j/{job.get('shortcode', '')}",
            "posted_at": job.get("created"),
        } for job in jobs_raw]
        return _jobs_result(jobs, board_url)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return FetchResult("transient_error", board_url)


def try_bamboohr(slug: str) -> FetchResult:
    board_url = f"https://{slug}.bamboohr.com/careers"
    api_url = f"https://{slug}.bamboohr.com/careers/list"
    try:
        response = requests.get(api_url, headers=HEADERS, timeout=10)
        time.sleep(SLEEP)
        if failure := _http_failure(response.status_code, board_url):
            return failure
        jobs_raw = response.json().get("result", [])
        if not isinstance(jobs_raw, list):
            return FetchResult("transient_error", board_url)
        jobs = []
        for job in jobs_raw:
            job_id = str(job.get("id", ""))
            jobs.append({
                "job_id": job_id,
                "title": job.get("title", {}).get("label", "") if isinstance(job.get("title"), dict) else str(job.get("title", "")),
                "department": job.get("department", {}).get("label", "") if isinstance(job.get("department"), dict) else str(job.get("department", "")),
                "location": job.get("location", {}).get("label", "") if isinstance(job.get("location"), dict) else str(job.get("location", "")),
                "job_url": f"{board_url}/{job_id}",
                "posted_at": None,
            })
        return _jobs_result(jobs, board_url)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return FetchResult("transient_error", board_url)


def try_ashby(slug: str) -> FetchResult:
    board_url = f"https://jobs.ashbyhq.com/{slug}"
    with _ashby_semaphore:
        try:
            response = None
            for attempt in range(3):
                response = requests.post(
                    ASHBY_GRAPHQL,
                    json={"operationName": "ApiJobBoardWithTeams", "variables": {"organizationHostedJobsPageName": slug}, "query": ASHBY_QUERY},
                    headers={**HEADERS, "Content-Type": "application/json"},
                    timeout=10,
                )
                time.sleep(SLEEP)
                if response.status_code != 429:
                    break
                if attempt < 2:
                    time.sleep(10 * (3 ** attempt))
            if response is None:
                return FetchResult("transient_error", board_url)
            if failure := _http_failure(response.status_code, board_url):
                return failure
            data = response.json()
            if data.get("errors"):
                return FetchResult("transient_error", board_url)
            board = data.get("data", {}).get("jobBoardWithTeams")
            if board is None:
                return FetchResult("not_found", board_url)
            teams = {team["id"]: team["name"] for team in board.get("teams", [])}
            jobs_raw = board.get("jobPostings", [])
            if not isinstance(jobs_raw, list):
                return FetchResult("transient_error", board_url)
            jobs = [{
                "job_id": job.get("id", ""),
                "title": job.get("title", ""),
                "department": teams.get(job.get("teamId", ""), ""),
                "location": job.get("locationName", ""),
                "job_url": f"{board_url}/{job.get('id', '')}",
                "posted_at": None,
            } for job in jobs_raw]
            return _jobs_result(jobs, board_url)
        except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError):
            return FetchResult("transient_error", board_url)


ATS_FETCHERS = {
    "greenhouse": try_greenhouse,
    "lever": try_lever,
    "ashby": try_ashby,
    "workable": try_workable,
    "bamboohr": try_bamboohr,
}
