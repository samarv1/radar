"""
Careers scraper orchestration + CLI.

Default mode: scrapes companies that have an EDGAR filing ≤ $100M (daily pipeline).
Hiring sweep mode (--hiring-sweep): scrapes ALL non-excluded accelerator companies
regardless of EDGAR status — used weekly to populate the Hiring section.

Tries Greenhouse → Lever → Ashby → Workable → BambooHR for each company.
Categorizes roles into Engineering / Product / GTM / Other.

Usage:
    uv run python -m scrapers.careers [--limit N] [--hiring-sweep]
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.connection import get_connection
from scrapers.careers.ats_fetchers import ATS_FETCHERS, REAL_ATS
from scrapers.careers.categorize import categorize
from scrapers.careers.db import (
    VALID_ACCELERATORS,
    clear_jobs,
    get_pending_companies,
    get_pending_standalone_websites,
    sync_jobs,
    update_careers_status,
    update_standalone_careers,
)
from scrapers.careers.discovery import discover_ats, is_likely_homepage, is_media_domain, slug_from_url

_print_lock = threading.Lock()


def _scrape_standalone_one(company: dict, total: int, idx: int) -> bool:
    """Scrape careers for a TC/standalone company. Saves to company_careers."""
    name = company["name"]
    website = company["website"]
    known_ats = company.get("careers_ats")
    known_url = company.get("careers_url")

    matched_ats = None
    matched_jobs = []
    matched_url = None
    fallback_careers_url = None

    valid_website = (
        bool(website)
        and is_likely_homepage(website)
        and not is_media_domain(website)
    )

    # Fast-path: ATS already known from a previous scrape.
    if known_ats in REAL_ATS and known_url:
        slug = slug_from_url(known_ats, known_url)
        if slug:
            result = ATS_FETCHERS[known_ats](slug)
            if result is not None:
                matched_jobs, matched_url = result
                matched_ats = known_ats

    if matched_ats is None:
        if valid_website:
            ats_name, slug, url = discover_ats(website)
            if ats_name:
                fetcher = ATS_FETCHERS.get(ats_name)
                if fetcher:
                    result = fetcher(slug)
                    if result is not None:
                        matched_jobs, matched_url = result
                        matched_ats = ats_name
                    else:
                        matched_ats = ats_name
                        matched_url = url
            elif url:
                fallback_careers_url = url
        elif website:
            with _print_lock:
                print(f"[{idx}/{total}] {name} (standalone) → skipped bad URL: {website}")

    conn = get_connection()
    try:
        if matched_ats:
            update_standalone_careers(conn, website, matched_ats, matched_url)
            conn.commit()
            cats = {}
            for j in matched_jobs:
                c = categorize(j["title"])
                cats[c] = cats.get(c, 0) + 1
            summary = " | ".join(f"{k}:{v}" for k, v in sorted(cats.items()))
            with _print_lock:
                print(f"[{idx}/{total}] {name} (standalone) → {matched_ats} ({len(matched_jobs)} jobs) [{summary}]")
            return True
        else:
            ats_status = "not_found" if valid_website else None
            update_standalone_careers(conn, website, ats_status, fallback_careers_url)
            conn.commit()
            with _print_lock:
                fallback_note = f" → {fallback_careers_url}" if fallback_careers_url else ""
                label = "not found" if valid_website else "no valid website"
                print(f"[{idx}/{total}] {name} (standalone) → {label}{fallback_note}")
            return False
    finally:
        conn.close()


def _scrape_one(company: dict, total: int, idx: int) -> bool:
    """Scrape a single company using its own DB connection. Returns True if found."""
    name = company["name"]
    website = company["website"]
    cid = company["id"]
    known_ats = company.get("careers_ats")
    known_url = company.get("careers_url")

    matched_ats = None
    matched_jobs = []
    matched_url = None
    fallback_careers_url = None

    valid_website = (
        bool(website)
        and is_likely_homepage(website)
        and not is_media_domain(website)
    )

    # Fast-path: ATS + slug already known — one API call, no discovery.
    # Falls through to full discovery if the fetch returns None (board moved/removed).
    if known_ats in REAL_ATS and known_url:
        slug = slug_from_url(known_ats, known_url)
        if slug:
            result = ATS_FETCHERS[known_ats](slug)
            if result is not None:
                matched_jobs, matched_url = result
                matched_ats = known_ats

    if matched_ats is None:
        if valid_website:
            ats_name, slug, url = discover_ats(website)
            if ats_name:
                fetcher = ATS_FETCHERS.get(ats_name)
                if fetcher:
                    result = fetcher(slug)
                    if result is not None:
                        matched_jobs, matched_url = result
                        matched_ats = ats_name
                    else:
                        matched_ats = ats_name
                        matched_url = url
            elif url:
                # Found a careers page but ATS isn't one we support — save the URL so
                # the UI can at least link to it with "apply ↗".
                fallback_careers_url = url
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
            # Preserve any fallback URL so the UI can show "apply ↗" even when we
            # can't count roles (e.g. company uses Rippling, Teamtailor, etc.).
            update_careers_status(conn, cid, ats_status, fallback_careers_url)
            conn.commit()
            with _print_lock:
                fallback_note = f" → {fallback_careers_url}" if fallback_careers_url else ""
                label = "not found" if valid_website else "no valid website"
                print(f"[{idx}/{total}] {name} → {label}{fallback_note}")
            return False
    finally:
        conn.close()


def _run_batch(items: list[dict], fn, workers: int) -> tuple[int, int]:
    """Run a scrape function over a list of items, returning (found, not_found)."""
    found = not_found = 0
    total = len(items)
    if workers <= 1:
        for i, item in enumerate(items):
            if fn(item, total, i + 1):
                found += 1
            else:
                not_found += 1
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(fn, item, total, i + 1): item
                for i, item in enumerate(items)
            }
            for future in as_completed(futures):
                try:
                    if future.result():
                        found += 1
                    else:
                        not_found += 1
                except Exception as e:
                    item = futures[future]
                    with _print_lock:
                        print(f"  ERROR {item.get('name', item.get('website', '?'))}: {e}")
                    not_found += 1
    return found, not_found


def scrape(
    limit: int | None = None,
    refresh_after_days: int | None = 3,
    rediscover_after_days: int | None = 21,
    hiring_sweep: bool = False,
    workers: int = 1,
    accelerator: str | None = None,
):
    conn = get_connection()
    try:
        companies = get_pending_companies(
            conn,
            refresh_after_days=refresh_after_days,
            rediscover_after_days=rediscover_after_days,
            hiring_sweep=hiring_sweep,
            accelerator=accelerator,
        )
        standalone = [] if hiring_sweep else get_pending_standalone_websites(
            conn,
            rediscover_after_days=rediscover_after_days,
        )
    finally:
        conn.close()

    if limit:
        companies = companies[:limit]
        standalone = standalone[:max(0, limit - len(companies))]

    mode = "hiring sweep" if hiring_sweep else "raised-feed"
    print(f"Scraping careers for {len(companies)} accelerator companies [{mode}] workers={workers}...")
    if standalone:
        print(f"Scraping careers for {len(standalone)} standalone/TC companies workers={workers}...")
    print()

    found, not_found = _run_batch(companies, _scrape_one, workers)

    if standalone:
        sf, snf = _run_batch(standalone, _scrape_standalone_one, workers)
        found += sf
        not_found += snf

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
            if not is_likely_homepage(url) or is_media_domain(url)
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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Only process first N companies")
    parser.add_argument("--hiring-sweep", action="store_true", help="Scrape all accelerator companies regardless of EDGAR status")
    parser.add_argument("--accelerator", choices=sorted(VALID_ACCELERATORS), help="Only scrape companies from this accelerator (e.g. yc, techstars)")
    parser.add_argument("--refresh-after-days", type=int, default=3, help="Re-fetch job listings for known-ATS companies scraped more than N days ago (default: 3)")
    parser.add_argument("--rediscover-after-days", type=int, default=75, help="Re-run full discovery for not_found companies scraped more than N days ago (default: 75)")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers (default: 1)")
    parser.add_argument("--reset-all", action="store_true", help="Wipe all ATS/careers data before re-scraping")
    parser.add_argument("--fix-websites", action="store_true", help="Clear bad website URLs (articles, media pages) so companies get re-scraped honestly")
    args = parser.parse_args()
    if args.reset_all:
        reset_careers_data()
    elif args.fix_websites:
        fix_bad_websites()
    else:
        scrape(
            limit=args.limit,
            refresh_after_days=args.refresh_after_days,
            rediscover_after_days=args.rediscover_after_days,
            hiring_sweep=args.hiring_sweep,
            workers=args.workers,
            accelerator=args.accelerator,
        )


if __name__ == "__main__":
    main()
