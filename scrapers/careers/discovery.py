"""
Website-first ATS discovery.

Crawls a company's own site for known careers-page paths and matches the
response URL/body against known ATS URL patterns (Greenhouse, Lever, Ashby,
Workable, BambooHR). No slug guessing: the slug always comes from the
company's own redirect chain or an embedded link.
"""

import re
import time
from urllib.parse import urlparse

import requests

from scrapers._common import DEFAULT_HEADERS

HEADERS = DEFAULT_HEADERS
SLEEP = 0.3

_ATS_PATTERNS = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/([^/?\s\"']+)", re.I)),
    # Some companies embed the Greenhouse API URL directly in their JS bundle
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([^/?\s\"']+)", re.I)),
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


def is_media_domain(url: str) -> bool:
    """Return True if the URL's domain is a known media/social/platform site."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc in _MEDIA_NETLOCS
    except Exception:
        return False


def is_likely_homepage(url: str) -> bool:
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


def discover_ats(website: str) -> tuple[str | None, str | None, str | None]:
    """Return (ats_name, slug, url) by following links from company's own website.

    When a recognized ATS is found: all three values are set.
    When a careers page is found but ATS is unrecognized: ats_name and slug are None,
    url is the careers page URL (so we can still surface a link to the user).
    When nothing is found: all three are None.

    No slug guessing — the slug comes directly from the company's own redirect
    chain or embedded link.
    """
    base = website.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    fallback_url: str | None = None

    for path in _CAREERS_PATHS:
        try:
            r = requests.get(base + path, headers=HEADERS, timeout=10, allow_redirects=True)
            time.sleep(SLEEP)
            for ats, pattern in _ATS_PATTERNS:
                m = pattern.search(r.url)
                if m:
                    slug = m.group(1).strip("/")
                    return ats, slug, _board_url(ats, slug)
            if r.status_code == 200 and len(r.content) < 2_000_000:
                for ats, pattern in _ATS_PATTERNS:
                    m = pattern.search(r.text)
                    if m:
                        slug = m.group(1).strip("/")
                        return ats, slug, _board_url(ats, slug)
                # Keep the first valid careers URL as fallback
                if fallback_url is None and not is_media_domain(r.url):
                    fallback_url = r.url
        except Exception:
            pass
    return None, None, fallback_url


def slug_from_url(ats: str, url: str) -> str | None:
    """Extract the ATS slug from a stored board URL using the same patterns as discovery."""
    for name, pattern in _ATS_PATTERNS:
        if name == ats:
            m = pattern.search(url)
            return m.group(1).strip("/") if m else None
    return None
