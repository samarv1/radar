"""
Pipeline runner.

Usage:
    uv run python main.py [--mode daily|weekly]

daily  (default): EDGAR → CIK lookup → cross-reference → careers → Product Hunt (last 2 days)
weekly           : all of the above + YC + all accelerator directories + PH full 90-day backfill
"""

import argparse

from scrapers.a16z import scrape as scrape_a16z
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
from scrapers.yc import scrape as scrape_yc


def run_daily():
    print("=== EDGAR filings ===")
    scrape_edgar()

    print("\n=== CIK lookup ===")
    run_cik_lookup()

    print("\n=== Cross-reference ===")
    run_cross_reference()

    print("\n=== Careers ===")
    scrape_careers()

    print("\n=== Product Hunt (last 2 days) ===")
    scrape_ph(days_back=2)

    print("\n=== TechCrunch (last 90 days) ===")
    scrape_techcrunch(days_back=90)


def run_weekly():
    print("=== Careers (refresh stale, 7-day window) ===")
    scrape_careers(rescrape_after_days=7)

    print("\n=== YC directory ===")
    scrape_yc()

    print("\n=== a16z Build ===")
    scrape_a16z()

    print("\n=== Sequoia ===")
    scrape_sequoia()

    print("\n=== Lightspeed ===")
    scrape_lightspeed()

    print("\n=== Pear ===")
    scrape_pear()

    print("\n=== Techstars ===")
    scrape_techstars()

    print("\n=== Product Hunt full backfill (90 days) ===")
    scrape_ph(days_back=90)


SCRAPERS = {
    "yc":        scrape_yc,
    "a16z":      scrape_a16z,
    "sequoia":   scrape_sequoia,
    "lightspeed": scrape_lightspeed,
    "pear":      scrape_pear,
    "techstars": scrape_techstars,
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
