"""Run a daily, weekly, or single-source pipeline mode."""

import argparse
from dataclasses import dataclass
from functools import partial
from typing import Callable

from db.migrate import run as apply_migrations
from scrapers.a16z import scrape as scrape_a16z
from scrapers.a16z_build import scrape as scrape_a16z_build
from scrapers.careers import scrape as scrape_careers
from scrapers.cik_lookup import run as run_cik_lookup
from scrapers.cross_reference import run as run_cross_reference
from scrapers.edgar import scrape_chunked as scrape_edgar_chunked, scrape_targeted as scrape_edgar_targeted
from scrapers.enrich_location import run as run_enrich_location
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


@dataclass(frozen=True)
class PipelineStep:
    name: str
    action: Callable[[], None]


def _step(name: str, action: Callable[[], None]) -> PipelineStep:
    return PipelineStep(name, action)


DAILY_STEPS = (
    _step("EDGAR filings (chunked, 60 days)", partial(scrape_edgar_chunked, days_back=60, chunk_days=30)),
    _step("CIK lookup", run_cik_lookup),
    _step("Cross-reference", run_cross_reference),
    _step("Careers (EDGAR-matched)", partial(scrape_careers, workers=4)),
    _step("a16z Build newsletter", partial(scrape_a16z_build, days_back=2)),
    _step("YC hiring signal", scrape_yc_hiring),
    _step(
        "Careers (accelerator companies - overlay refresh + new discovery)",
        partial(scrape_careers, hiring_sweep=True, workers=12, limit=500),
    ),
    _step("Product Hunt (last 2 days)", partial(scrape_ph, days_back=2)),
    _step("TechCrunch (last 2 days)", partial(scrape_techcrunch, days_back=2)),
    _step("Signalbase (last 2 days)", partial(scrape_signalbase, days_back=2)),
    _step("Standalone validation", run_validate_standalone),
    _step("EDGAR enrichment", run_enrich_edgar),
)

WEEKLY_STEPS = (
    _step("YC directory", scrape_yc),
    _step("a16z directory", scrape_a16z),
    _step("Sequoia", scrape_sequoia),
    _step("Lightspeed", scrape_lightspeed),
    _step("Pear", scrape_pear),
    _step("Techstars", scrape_techstars),
    _step("CIK lookup", run_cik_lookup),
    _step("EDGAR broad scan (180 days)", partial(scrape_edgar_chunked, days_back=180, chunk_days=30)),
    _step("EDGAR targeted (accelerator cohort, 180 days)", partial(scrape_edgar_targeted, days_back=180)),
    _step("Cross-reference", run_cross_reference),
    _step("HQ location enrichment (non-YC/Techstars, via matched EDGAR filings)", run_enrich_location),
    _step("Careers (EDGAR-matched)", partial(scrape_careers, workers=4)),
    _step("a16z Build newsletter", partial(scrape_a16z_build, days_back=2)),
    _step("YC hiring signal", scrape_yc_hiring),
    _step(
        "Careers (accelerator companies - overlay refresh, no limit)",
        partial(scrape_careers, hiring_sweep=True, workers=12),
    ),
    _step("Product Hunt backfill (30 days)", partial(scrape_ph, days_back=30)),
    _step("TechCrunch full backfill (180 days)", partial(scrape_techcrunch, days_back=180)),
    _step("Signalbase full backfill (180 days)", partial(scrape_signalbase, days_back=180)),
    _step("Standalone validation", run_validate_standalone),
    _step("EDGAR enrichment", run_enrich_edgar),
)

SINGLE_MODES = {
    "yc": _step("YC directory", scrape_yc),
    "a16z": _step("a16z directory", scrape_a16z),
    "sequoia": _step("Sequoia", scrape_sequoia),
    "lightspeed": _step("Lightspeed", scrape_lightspeed),
    "pear": _step("Pear", scrape_pear),
    "techstars": _step("Techstars", scrape_techstars),
    "careers-rescrape": _step(
        "Careers (accelerator companies - capped rescrape)",
        partial(scrape_careers, hiring_sweep=True, workers=12, limit=500),
    ),
    "signalbase": _step("Signalbase full backfill (180 days)", partial(scrape_signalbase, days_back=180, workers=20)),
    "edgar-broad-backfill": _step(
        "EDGAR broad scan (180 days)", partial(scrape_edgar_chunked, days_back=180, chunk_days=30)
    ),
    "edgar-targeted-backfill": _step(
        "EDGAR targeted (accelerator cohort, 180 days)", partial(scrape_edgar_targeted, days_back=180)
    ),
    "techcrunch-backfill": _step(
        "TechCrunch full backfill (180 days)", partial(scrape_techcrunch, days_back=180)
    ),
    "ph-backfill": _step("Product Hunt backfill (30 days)", partial(scrape_ph, days_back=30)),
}


def get_steps(mode: str) -> tuple[PipelineStep, ...]:
    if mode == "daily":
        return DAILY_STEPS
    if mode == "weekly":
        return WEEKLY_STEPS
    return (SINGLE_MODES[mode],)


def run_mode(mode: str) -> None:
    for index, step in enumerate(get_steps(mode)):
        prefix = "" if index == 0 else "\n"
        print(f"{prefix}=== {step.name} ===")
        step.action()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly", *SINGLE_MODES.keys()],
        default="daily",
        help=(
            "'daily': current discovery and enrichment windows; "
            "'weekly': directory refreshes plus wider source windows; "
            "or a single scraper name to run just that one"
        ),
    )
    args = parser.parse_args()

    print("=== Schema ===")
    apply_migrations()
    run_mode(args.mode)
