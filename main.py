"""
Pipeline runner.

Usage:
    uv run python main.py [--mode daily|weekly]

daily  (default): EDGAR → CIK lookup → cross-reference → careers → Product Hunt (last 2 days)
weekly           : all of the above + YC + all accelerator directories + 180-day backfill for all funding sources
"""

import argparse

from scrapers.a16z import scrape as scrape_a16z
from scrapers.a16z_build import scrape as scrape_a16z_build
from scrapers.careers import scrape as scrape_careers
from scrapers.cik_lookup import run as run_cik_lookup
from scrapers.cross_reference import run as run_cross_reference
from scrapers.edgar import scrape as scrape_edgar, scrape_chunked as scrape_edgar_chunked, scrape_targeted as scrape_edgar_targeted
from scrapers.lightspeed import scrape as scrape_lightspeed
from scrapers.pear import scrape as scrape_pear
from scrapers.producthunt import scrape as scrape_ph
from scrapers.sequoia import scrape as scrape_sequoia
from scrapers.signalbase import scrape as scrape_signalbase
from scrapers.techcrunch import scrape as scrape_techcrunch
from scrapers.techstars import scrape as scrape_techstars
from scrapers.validate_standalone import run as run_validate_standalone
from scrapers.enrich_edgar import run as run_enrich_edgar
from scrapers.yc import scrape as scrape_yc
from scrapers.yc_hiring import scrape as scrape_yc_hiring


def run_daily():
    print("=== EDGAR filings (chunked, 60 days) ===")
    scrape_edgar_chunked(days_back=60, chunk_days=30)

    print("\n=== CIK lookup ===")
    run_cik_lookup()

    print("\n=== Cross-reference ===")
    run_cross_reference()

    print("\n=== Careers (EDGAR-matched) ===")
    scrape_careers(workers=4)

    print("\n=== a16z Build newsletter ===")
    scrape_a16z_build(days_back=2)

    print("\n=== YC hiring signal ===")
    scrape_yc_hiring()

    print("\n=== Careers (accelerator companies — overlay refresh + new discovery) ===")
    # Known-ATS companies: cheap 1-request refresh every 3 days.
    # NULL companies: discovered once on pickup.
    # not_found companies: re-discovery every 75 days.
    # Cap at 500/day so the step stays bounded; backlog drains over a few runs.
    scrape_careers(hiring_sweep=True, workers=12, limit=500)

    print("\n=== Product Hunt (last 2 days) ===")
    scrape_ph(days_back=2)

    print("\n=== TechCrunch (last 2 days) ===")
    scrape_techcrunch(days_back=2)

    print("\n=== Signalbase (last 2 days) ===")
    scrape_signalbase(days_back=2)

    print("\n=== Standalone validation ===")
    run_validate_standalone()

    print("\n=== EDGAR enrichment ===")
    run_enrich_edgar()


def run_weekly():
    print("=== YC directory ===")
    scrape_yc()

    print("\n=== a16z directory ===")
    scrape_a16z()

    print("\n=== Sequoia ===")
    scrape_sequoia()

    print("\n=== Lightspeed ===")
    scrape_lightspeed()

    print("\n=== Pear ===")
    scrape_pear()

    print("\n=== Techstars ===")
    scrape_techstars()

    print("\n=== EDGAR broad scan (180 days) ===")
    # Extends the daily 60-day broad scan to catch filings from the full 6-month window.
    scrape_edgar_chunked(days_back=180, chunk_days=30)

    print("\n=== EDGAR targeted (accelerator cohort, 180 days) ===")
    # Pulls full 6-month filing history for each known-CIK company directly
    # from the EDGAR submissions API — bypasses the broad scan's 10k pagination limit.
    scrape_edgar_targeted(days_back=180)

    print("\n=== Careers (accelerator companies — overlay refresh, no limit) ===")
    # Weekly runs the full cohort without a cap: known-ATS companies are cheap (1 request each),
    # not_found companies re-discover only if >75 days stale.
    scrape_careers(hiring_sweep=True, workers=12)

    print("\n=== Product Hunt full backfill (180 days) ===")
    scrape_ph(days_back=180)

    print("\n=== TechCrunch full backfill (180 days) ===")
    scrape_techcrunch(days_back=180)

    print("\n=== Signalbase full backfill (180 days) ===")
    scrape_signalbase(days_back=180)


SCRAPERS = {
    "yc":        scrape_yc,
    "a16z":      scrape_a16z,
    "sequoia":   scrape_sequoia,
    "lightspeed": scrape_lightspeed,
    "pear":      scrape_pear,
    "techstars": scrape_techstars,
    # Capped like the daily hiring sweep: the full cohort had grown past what
    # fits in the 30-min job timeout, so this drains the backlog over multiple
    # weekly runs instead of trying everything at once (see July 20 2026 timeout).
    "careers-rescrape": lambda: scrape_careers(hiring_sweep=True, workers=12, limit=500),
    "signalbase": lambda: scrape_signalbase(days_back=180, workers=20),
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly", *SCRAPERS.keys()],
        default="daily",
        help=(
            "'daily': EDGAR + careers + PH; "
            "'weekly': all accelerator dirs + full PH backfill + daily; "
            "or a single scraper name to run just that one"
        ),
    )
    args = parser.parse_args()

    if args.mode in SCRAPERS:
        SCRAPERS[args.mode]()
    elif args.mode == "weekly":
        run_weekly()
        run_daily()
    else:
        run_daily()
