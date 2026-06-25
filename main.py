"""
Pipeline runner.

Usage:
    uv run python main.py [--mode daily|weekly]

daily  (default): EDGAR → CIK lookup → cross-reference → careers → Product Hunt (last 2 days)
weekly           : all of the above + YC + all accelerator directories + PH full 90-day backfill
"""

import argparse

from scrapers.a16z import scrape as scrape_a16z
from scrapers.a16z_build import scrape as scrape_a16z_build
from scrapers.careers import scrape as scrape_careers
from scrapers.cik_lookup import run as run_cik_lookup
from scrapers.cross_reference import run as run_cross_reference
from scrapers.edgar import scrape as scrape_edgar
from scrapers.lightspeed import scrape as scrape_lightspeed
from scrapers.pear import scrape as scrape_pear
from scrapers.producthunt import scrape as scrape_ph
from scrapers.sequoia import scrape as scrape_sequoia
from scrapers.techcrunch import scrape as scrape_techcrunch
from scrapers.techstars import scrape as scrape_techstars
from scrapers.validate_standalone import run as run_validate_standalone
from scrapers.enrich_edgar import run as run_enrich_edgar
from scrapers.yc import scrape as scrape_yc
from scrapers.yc_hiring import scrape as scrape_yc_hiring


def run_daily():
    print("=== EDGAR filings ===")
    scrape_edgar()

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

    print("\n=== Careers (new accelerator companies) ===")
    # Only touches companies with NULL careers_scraped_at — fast daily pass.
    # a16z_build and yc_hiring reset careers_scraped_at for signalled companies.
    # Cap at 500/day so the step stays bounded; backlog drains over a few runs.
    scrape_careers(hiring_sweep=True, workers=8, limit=500)

    print("\n=== Product Hunt (last 2 days) ===")
    scrape_ph(days_back=2)

    print("\n=== TechCrunch (last 2 days) ===")
    scrape_techcrunch(days_back=2)

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

    print("\n=== Careers (30-day rescrape) ===")
    # Re-checks companies whose hiring status is >30 days stale.
    scrape_careers(hiring_sweep=True, rescrape_after_days=30, workers=8)

    print("\n=== Product Hunt full backfill (90 days) ===")
    scrape_ph(days_back=90)

    print("\n=== TechCrunch full backfill (90 days) ===")
    scrape_techcrunch(days_back=90)


SCRAPERS = {
    "yc":        scrape_yc,
    "a16z":      scrape_a16z,
    "sequoia":   scrape_sequoia,
    "lightspeed": scrape_lightspeed,
    "pear":      scrape_pear,
    "techstars": scrape_techstars,
    "careers-rescrape": lambda: scrape_careers(hiring_sweep=True, rescrape_after_days=30, workers=8),
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
