# Startup Sourcing Tool

A data pipeline that helps students find recently funded startups *before* they post jobs — then understand each company well enough to write a cold email that actually lands.

The core insight: the first 60–90 days after a startup closes a funding round is the best window to reach out. They have money and conviction, the founder still reads their own email, and the recruiting machine hasn't started yet. Most students miss this window entirely because they're browsing job boards, which are weeks or months behind.

---

## What It Does

The tool aggregates multiple free public signals into two feeds:

### Raised tab
Companies that have recently closed a funding round, surfaced from:

**1. SEC EDGAR Form D filings** — Any US company that raises venture capital must file a Form D with the SEC within 15 days of closing. This is fully public, completely free, and often surfaces deals weeks before they hit TechCrunch. We poll the EDGAR API and filter for US operating companies (excluding real estate, oil & gas, banking, and financial partnerships). Companies that raised over $100M are excluded — cold outreach loses its edge at that stage.

**2. Accelerator & VC portfolio directories** — We scrape public company directories across six sources to build a database of ~10,000 companies that have cleared a quality bar:
- Y Combinator
- a16z
- Sequoia Capital
- Pear VC
- Lightspeed Venture Partners
- Techstars (US cohorts, 2018+)

**3. Cross-reference** — The highest-value signal comes from combining the two above. A company in any of the above directories that just filed a Form D = quality-filtered startup with fresh capital. We use CIK lookup + fuzzy name matching to link the two datasets.

**3b. Standalone EDGAR ("Other Technology")** — EDGAR filings in the `Other Technology` industry group that don't match any accelerator directory are surfaced directly as their own category. This catches VC-backed tech startups that have no accelerator affiliation. Each filing is enriched with an investor count parsed from the Form D XML (`enrich_edgar.py`) — a small count (under ~20) suggests an institutional round rather than crowdfunding or friends-and-family.

**4. TechCrunch funding news** — We scrape TechCrunch's venture category via their WordPress API and parse funding announcements. Company names are extracted from article titles and body content (via hyperlink parsing), with slug-based fallback. This catches companies that raised but aren't in any accelerator directory. Companies that appear in both TC and EDGAR get the EDGAR filing as the canonical record ("raised"); TC-only companies are labeled "announced."

**4b. Signalbase funding news** — Same idea as TechCrunch, sourced from trysignalbase.com's public sitemap instead. Parses company name/amount/round from JSON-LD + meta tags on each funding page and upserts into the same `funding_news` table (`source='signalbase'`), so it feeds the "announced" category alongside TC.

**5. Product Hunt launches** — Pulled via GraphQL API (last 90 days, ≥50 upvotes) and used as a cross-reference validation signal to confirm EDGAR filers are real tech companies. Not surfaced as a standalone feed source (too noisy).

### Actively Hiring tab
Early-stage accelerator-backed companies with confirmed open roles scraped directly from their ATS. A company appears here when:
- It has live job listings on Greenhouse, Lever, Ashby, Workable, or BambooHR
- It does not already appear in the Raised tab (no EDGAR filing in the last 90 days)
- It has not raised over $100M

Role counts are broken down by type (Eng/Product/GTM/Other) and level (Intern/New Grad), enabling targeted filtering. Cards show a grad cap icon when intern or new grad roles are available, and an apply link when a confirmed ATS URL exists.

---

## Data Sources

| Source | Method |
|--------|--------|
| SEC EDGAR Form D | EDGAR full-text search + submissions API |
| Y Combinator | Scrape `ycombinator.com/companies` + Algolia hiring signal |
| a16z | RSS + portfolio page |
| Sequoia | WordPress REST API |
| Pear VC | Portfolio page scrape |
| Lightspeed | Embedded JS + sitemap |
| Techstars | Typesense API (public token) |
| Product Hunt | GraphQL API (requires free dev token) |
| TechCrunch | WordPress REST API |
| Signalbase | Sitemap scrape (trysignalbase.com) |
| ATS (Greenhouse/Lever/Ashby/Workable/BambooHR) | Public job board APIs |

---

## Pipeline Architecture

```
EDGAR broad scan ────────────────────────────────────┐
                                                      ├──► cross_reference.py ──► edgar_filings.accelerator_id
Accelerator/VC scrapers ─────────────────────────────┘         │
         │                                                      │
         └──► cik_lookup.py ──► accelerator_companies.edgar_cik │
                                                                │
validate_standalone.py ─────────────────────────────────────────┘
  marks "Other Technology" filings (standalone_source='edgar')
  marks TC/PH cross-reference matches (standalone_source='techcrunch')

enrich_edgar.py ──────────────────────────────────────► investor_count, vc_firm_signal
enrich_websites.py ───────────────────────────────────► accelerator_companies.website (Lightspeed, Sequoia)

Product Hunt API ──────────────────────────────────────► ph_launches (cross-reference only)
TechCrunch WP API ─────────────────────────────────────► funding_news table
Signalbase sitemap scrape ─────────────────────────────► funding_news table

yc_hiring.py ─────────────────────────────────────────► resets careers_scraped_at for YC isHiring companies
careers.py ───────────────────────────────────────────► job_listings (Greenhouse/Lever/Ashby/Workable/BambooHR)
  --hiring-sweep: all early-stage accelerator companies regardless of EDGAR status
  --rescrape-after-days N: re-check companies whose data is older than N days
  --workers N: parallel scraping (default 1)
```

The careers scraper uses **diff-based sync**: new job IDs get `first_seen_at = NOW()`; removed IDs are deleted; existing rows keep their original `first_seen_at`. This preserves job history across rescrapes and enables accurate "last posted" dating.

The feed query in `web/lib/db.ts` unions four branches for the Raised tab:
1. **Accelerator + EDGAR** — highest confidence; shows accelerator badge + "raised" label
2. **Standalone EDGAR** — "Other Technology" filings not matched to any accelerator; "None / Unknown" badge
3. **TC-only** — TechCrunch announcements with no Form D yet; "None / Unknown" badge + "announced" label
4. **Accelerator + TC announced** — accelerator-matched companies with a TC announcement but no Form D yet; shows real accelerator badge + "announced" label

The Actively Hiring tab is a separate query (`getHiringFeed`) that joins `accelerator_companies` with `job_listings` and applies early-stage filters per accelerator.

The frontend is a Next.js app (`web/`) that reads directly from the same Postgres database and renders filterable feeds. Raised tab filters: Accelerator, Hiring status, days since filing, amount raised. Hiring tab filters: Accelerator, Role Type (Eng/Product/GTM/Other), Role Level (Intern/New Grad/Other).

---

## Deployment

The pipeline runs automatically via GitHub Actions:

- **Daily (7am UTC):** EDGAR → CIK lookup → cross-reference → careers (EDGAR-matched) → a16z Build newsletter → YC hiring signal → careers sweep (new companies only) → Product Hunt → TechCrunch → Signalbase → standalone validation → EDGAR enrichment
- **Weekly (Monday):** Re-scrapes all accelerator directories (YC, a16z, Sequoia, Lightspeed, Pear, Techstars) + 30-day careers rescrape + full PH backfill + full Signalbase backfill (180 days)
- **Monday 12pm UTC:** Standalone 30-day careers rescrape (all accelerator companies, stale > 30 days)

To trigger a run manually:
```bash
gh workflow run pipeline.yml -f mode=daily
gh workflow run pipeline.yml -f mode=weekly
gh workflow run pipeline.yml -f mode=careers-rescrape
gh workflow run pipeline.yml -f mode=signalbase
# or: yc, a16z, sequoia, lightspeed, pear, techstars
```

---

## Database Migrations

`db/schema.sql` covers the original tables only. Run migrations in order (after `apply_schema()`) when setting up a new database:

```bash
uv run python -c "from db.connection import apply_schema; apply_schema()"
uv run python db/migrate.py
```

`db/migrate.py` compiles all migrations (v2-v15) into one script and runs them in order. All migrations use `IF NOT EXISTS`-style DDL (or, for v12, a data-fix `UPDATE` that's a no-op on an empty table), so it's safe to run start-to-finish against a brand-new database, or to re-run against one that's already partially migrated. The individual `db/migrate_v*.py` files are kept for history/reference.

---

## Local Setup

**Pipeline:**
```bash
uv sync
cp .env.example .env   # set DATABASE_URL (local dev Postgres) and PH_API_TOKEN

uv run python main.py --mode daily
uv run python main.py --mode weekly
uv run python validate.py

# Careers scraper options:
uv run python scrapers/careers.py --hiring-sweep --workers 8
uv run python scrapers/careers.py --hiring-sweep --rescrape-after-days 30 --workers 8
uv run python scrapers/yc_hiring.py   # reset YC isHiring companies for next careers sweep

# Enrich missing website URLs (run once after scraping Lightspeed/Sequoia):
uv run python scrapers/enrich_websites.py --accelerator lightspeed
uv run python scrapers/enrich_websites.py --accelerator sequoia
```

**Frontend:**
```bash
cd web
npm install
npm run dev   # reads DATABASE_URL from ../.env
```

---

## Promoting Local Data to Production

The separate Railway staging environment (staging branch + isolated Postgres) has been rolled back — it added deploy overhead without much payoff. Instead, test scraper changes against your local DB and promote the resulting rows straight into production with `db/promote.py`, without re-running scrapers a second time against prod.

**Setup:** set `PROD_DATABASE_URL` in `.env` alongside your local `DATABASE_URL`.

**Usage:**
```bash
uv run python db/promote.py
```

This applies the schema + all migrations against the target first, then copies new rows table-by-table (`accelerator_companies` → `edgar_filings`, `ph_launches`, `funding_news`, `job_listings`, `company_careers`), remapping local FK ids to their production equivalents along the way (matched on each table's own unique constraint, e.g. `source_url` for companies). Inserts use `ON CONFLICT ... DO NOTHING`, so it never overwrites existing production rows and is always safe to re-run. It refuses to run if `DATABASE_URL` and `PROD_DATABASE_URL` are identical.

The cron pipeline in `.github/workflows/pipeline.yml` is unaffected — it always runs against production's `DATABASE_URL` secret directly.
