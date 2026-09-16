"""Careers scraper orchestration and CLI.

Default mode covers raised-feed companies. Hiring sweep mode covers all eligible
accelerator companies. Known boards are fetched directly before site discovery.

Usage:
    uv run python -m scrapers.careers [--limit N] [--hiring-sweep]
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Literal

from db.connection import get_connection
from scrapers.careers.ats_fetchers import ATS_FETCHERS, REAL_ATS, FetchResult
from scrapers.careers.categorize import categorize
from scrapers.careers.db import (
    VALID_ACCELERATORS,
    get_pending_companies,
    get_pending_standalone_websites,
    sync_jobs,
    update_careers_status,
    update_standalone_careers,
)
from scrapers.careers.discovery import discover_ats_result, is_likely_homepage, is_media_domain, slug_from_url

_print_lock = threading.Lock()


@dataclass(frozen=True)
class CareersResolution:
    status: Literal["success", "empty", "not_found", "transient_error"]
    ats: str | None = None
    url: str | None = None
    jobs: list[dict] | None = None
    checked_website: bool = False


def _from_fetch(ats: str, result: FetchResult, checked_website: bool) -> CareersResolution:
    return CareersResolution(
        status=result.status,
        ats=ats,
        url=result.board_url,
        jobs=result.jobs,
        checked_website=checked_website,
    )


def resolve_careers(company: dict) -> CareersResolution:
    """Resolve a company to one authoritative board outcome."""
    website = company["website"]
    known_ats = company.get("careers_ats")
    known_url = company.get("careers_url")
    valid_website = (
        bool(website)
        and is_likely_homepage(website)
        and not is_media_domain(website)
    )

    if known_ats in REAL_ATS and known_url:
        slug = slug_from_url(known_ats, known_url)
        if slug:
            result = ATS_FETCHERS[known_ats](slug)
            if result.status != "not_found":
                return _from_fetch(known_ats, result, valid_website)

    if not valid_website:
        return CareersResolution("not_found")

    discovery = discover_ats_result(website)
    if discovery.status == "transient_error":
        return CareersResolution("transient_error")
    if not discovery.ats or not discovery.slug:
        return CareersResolution("not_found", url=discovery.url, checked_website=True)

    result = ATS_FETCHERS[discovery.ats](discovery.slug)
    return _from_fetch(discovery.ats, result, checked_website=True)


def _job_summary(jobs: list[dict]) -> str:
    counts: dict[str, int] = {}
    for job in jobs:
        category = categorize(job["title"])
        counts[category] = counts.get(category, 0) + 1
    return " | ".join(f"{key}:{value}" for key, value in sorted(counts.items()))


def _scrape_standalone_one(company: dict, total: int, idx: int, conn=None) -> bool:
    name = company["name"]
    website = company["website"]
    resolution = resolve_careers(company)
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        if resolution.status == "transient_error":
            conn.rollback()
            with _print_lock:
                print(f"[{idx}/{total}] {name} (standalone) → temporary fetch error")
            return False
        if resolution.status in {"success", "empty"}:
            update_standalone_careers(conn, website, resolution.ats, resolution.url)
            conn.commit()
            jobs = resolution.jobs or []
            with _print_lock:
                print(f"[{idx}/{total}] {name} (standalone) → {resolution.ats} ({len(jobs)} jobs) [{_job_summary(jobs)}]")
            return True

        status = "not_found" if resolution.checked_website else None
        update_standalone_careers(conn, website, status, resolution.url)
        conn.commit()
        with _print_lock:
            fallback_note = f" → {resolution.url}" if resolution.url else ""
            label = "not found" if resolution.checked_website else "no valid website"
            print(f"[{idx}/{total}] {name} (standalone) → {label}{fallback_note}")
        return False
    finally:
        if owns_connection:
            conn.close()


def _scrape_one(company: dict, total: int, idx: int, conn=None) -> bool:
    name = company["name"]
    cid = company["id"]
    resolution = resolve_careers(company)
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        if resolution.status == "transient_error":
            conn.rollback()
            with _print_lock:
                print(f"[{idx}/{total}] {name} → temporary fetch error")
            return False
        if resolution.status in {"success", "empty"}:
            jobs = resolution.jobs or []
            sync_jobs(conn, cid, resolution.ats, jobs)
            update_careers_status(conn, cid, resolution.ats, resolution.url)
            conn.commit()
            with _print_lock:
                print(f"[{idx}/{total}] {name} → {resolution.ats} ({len(jobs)} jobs) [{_job_summary(jobs)}]")
            return True

        status = "not_found" if resolution.checked_website else None
        update_careers_status(conn, cid, status, resolution.url)
        conn.commit()
        with _print_lock:
            fallback_note = f" → {resolution.url}" if resolution.url else ""
            label = "not found" if resolution.checked_website else "no valid website"
            print(f"[{idx}/{total}] {name} → {label}{fallback_note}")
        return False
    finally:
        if owns_connection:
            conn.close()


def _run_chunk(indexed_items: list[tuple[int, dict]], total: int, fn) -> tuple[int, int]:
    found = not_found = 0
    conn = get_connection()
    try:
        for index, item in indexed_items:
            try:
                if fn(item, total, index, conn=conn):
                    found += 1
                else:
                    not_found += 1
            except Exception as error:
                conn.rollback()
                with _print_lock:
                    print(f"  ERROR {item.get('name', item.get('website', '?'))}: {error}")
                not_found += 1
    finally:
        conn.close()
    return found, not_found


def _run_batch(items: list[dict], fn, workers: int) -> tuple[int, int]:
    """Run a scrape batch with one reusable database connection per worker."""
    total = len(items)
    if not items:
        return 0, 0

    indexed = list(enumerate(items, start=1))
    worker_count = min(max(workers, 1), total)
    chunks = [indexed[offset::worker_count] for offset in range(worker_count)]
    if worker_count == 1:
        return _run_chunk(chunks[0], total, fn)

    found = not_found = 0
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_run_chunk, chunk, total, fn): chunk for chunk in chunks}
        for future in as_completed(futures):
            try:
                chunk_found, chunk_not_found = future.result()
                found += chunk_found
                not_found += chunk_not_found
            except Exception as error:
                chunk = futures[future]
                with _print_lock:
                    print(f"  ERROR worker starting at item {chunk[0][0]}: {error}")
                not_found += len(chunk)
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
