# Startup Sourcing Tool

A data pipeline that helps students find recently funded startups *before* they post jobs — then understand each company well enough to write a cold email that actually lands.

The core insight: the first 60–90 days after a startup closes a funding round is the best window to reach out. They have money and conviction, the founder still reads their own email, and the recruiting machine hasn't started yet. Most students miss this window entirely because they're browsing job boards, which are weeks or months behind.

---

## What It Does

The tool aggregates multiple free public signals into a single feed:

**1. SEC EDGAR Form D filings** — Any US company that raises venture capital must file a Form D with the SEC within 15 days of closing. This is fully public, completely free, and often surfaces deals weeks before they hit TechCrunch. We poll the EDGAR API and filter for US operating companies (excluding real estate, oil & gas, banking, and financial partnerships). Companies that raised over $100M are excluded — cold outreach loses its edge at that stage.

**2. Accelerator & VC portfolio directories** — We scrape public company directories across six sources to build a database of ~10,000 companies that have cleared a quality bar:
- Y Combinator
- a16z
- Sequoia Capital
- Pear VC
- Lightspeed Venture Partners
- Techstars (US cohorts, 2018+)

**3. Cross-reference** — The highest-value signal comes from combining the two above. A company in any of the above directories that just filed a Form D = quality-filtered startup with fresh capital. We use CIK lookup + fuzzy name matching to link the two datasets.

**4. Product Hunt launches** — We pull recent launches (last 90 days, ≥50 upvotes) from the PH API. A company that launched on PH recently is actively shipping and likely in growth mode — a good cold outreach trigger even without an EDGAR filing.

**5. TechCrunch funding news** — We scrape TechCrunch's venture category via their WordPress API and parse funding announcements (company name, amount, round type). This catches companies that raised but aren't in any accelerator directory.

---

## Data Sources

| Source | Method |
|--------|--------|
| SEC EDGAR Form D | EDGAR full-text search + submissions API |
| Y Combinator | Scrape `ycombinator.com/companies` |
| a16z | RSS + portfolio page |
| Sequoia | WordPress REST API |
| Pear VC | Portfolio page scrape |
| Lightspeed | Embedded JS + sitemap |
| Techstars | Typesense API (public token) |
| Product Hunt | GraphQL API (requires free dev token) |
| TechCrunch | WordPress REST API |

---

## Pipeline Architecture

```
EDGAR broad scan ────────────────────────────────────┐
                                                      ├──► cross_reference.py ──► edgar_filings.accelerator_id
Accelerator/VC scrapers ─────────────────────────────┘
         │
         └──► cik_lookup.py ──► accelerator_companies.edgar_cik
                  │
                  └──► edgar.py --mode targeted ──► precise per-company filings

Product Hunt API ──────────────────────────────────────► ph_launches table

TechCrunch WP API ─────────────────────────────────────► funding_news table
```

All data lives in Postgres. `validate.py` checks data quality and acceptance criteria.

The frontend is a Next.js app (`web/`) that reads directly from the same Postgres database and renders a filterable feed of companies.

---

## Deployment

The pipeline runs automatically via GitHub Actions:

- **Daily (7am UTC):** EDGAR → CIK lookup → cross-reference → careers → Product Hunt → TechCrunch
- **Monday:** Re-scrapes all accelerator directories (YC, a16z, Sequoia, Lightspeed, Pear, Techstars) + full PH backfill

The database is hosted on Railway. GitHub Actions connects via the public Railway URL stored as `DATABASE_URL` in repo secrets.

To trigger a run manually:
```bash
gh workflow run pipeline.yml -f mode=daily   # or: weekly, yc, a16z, sequoia, lightspeed, pear, techstars
```

---

## Local Setup

**Pipeline:**
```bash
uv sync
cp .env.example .env   # set DATABASE_URL (Railway public URL) and PH_API_TOKEN

uv run python main.py --mode daily
uv run python main.py --mode weekly
uv run python validate.py
```

**Frontend:**
```bash
cd web
npm install
npm run dev   # reads DATABASE_URL from ../.env
```
