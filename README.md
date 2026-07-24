# Startup Sourcing Tool

A data pipeline that helps students find recently funded startups *before* they post jobs.

The core idea: the first 60–90 days after a startup closes a funding round is the best window to reach out. They have money and conviction, the founder still reads their own email, and they haven't heavily begun recruiting. Most students miss this window because they're browsing job boards, which are weeks or months behind.

---

## Tech stack

- **Scrapers/pipeline:** Python
- **Database:** Postgres, hosted on Railway
- **Frontend:** Next.js 16, TypeScript, Tailwind, shadcn/ui
- **Infra:** GitHub Actions for scheduling, Vercel for the frontend

## Project structure

```
.
├── main.py          # pipeline entrypoint (daily/weekly modes)
├── scrapers/        # one file per data source (EDGAR, YC, a16z, TechCrunch, careers pages, etc.)
├── db/              # schema, migrations, connection helper, local→prod promote script
└── web/             # Next.js frontend, reads directly from Postgres
```

---

## What it does

The tool aggregates a handful of free public signals into two feeds:

### Raised tab

Companies that recently closed a funding round, pulled from:

- **SEC EDGAR Form D filings** — any US company raising venture capital has to file a Form D within 15 days of closing, and it's fully public. We poll EDGAR and filter out non-operating stuff (real estate, oil & gas, banking) and anything over $100M raised.
- **Accelerator & VC portfolio directories** — YC, a16z, Sequoia, Pear, Lightspeed, and Techstars, scraped into a database of ~10,000 companies that have already cleared some quality bar.
- **Cross-referencing the two** — the real signal is a company that's *both* in a portfolio directory *and* just filed a Form D. We link them with CIK lookup + fuzzy name matching.
- **Standalone EDGAR filings** — tech-industry Form D filings that don't match any accelerator directory, shown as their own category so we're not only surfacing accelerator alumni.
- **TechCrunch and Signalbase funding news** — catches companies that raised but never show up in an accelerator directory.
- **Product Hunt launches** — used quietly in the background to help confirm EDGAR filers are real tech companies, not surfaced as its own feed.

### Actively Hiring tab

Early-stage accelerator-backed companies with confirmed open roles on Greenhouse, Lever, Ashby, Workable, or BambooHR. These are specifically ones that *haven't* filed a Form D recently and haven't raised over $100M, so it doesn't just duplicate the Raised tab. Roles are broken down by type (Eng/Product/GTM/Other) and level (Intern/New Grad), and cards flag when intern/new-grad roles are open.

---

## Data sources

| Source                                         | Method                                                     |
| ---------------------------------------------- | ---------------------------------------------------------- |
| SEC EDGAR Form D                               | EDGAR full-text search + submissions API                   |
| Y Combinator                                   | Scrape `ycombinator.com/companies` + Algolia hiring signal |
| a16z                                           | RSS + portfolio page                                       |
| Sequoia                                        | WordPress REST API                                         |
| Pear VC                                        | Portfolio page scrape                                      |
| Lightspeed                                     | Embedded JS + sitemap                                      |
| Techstars                                      | Typesense API (public token)                               |
| Product Hunt                                   | GraphQL API (requires free dev token)                      |
| TechCrunch                                     | WordPress REST API                                         |
| Signalbase                                     | Sitemap scrape (trysignalbase.com)                         |
| ATS (Greenhouse/Lever/Ashby/Workable/BambooHR) | Public job board APIs                                      |

---

## How it fits together

Scrapers write into a shared Postgres schema. A cross-reference step links accelerator-directory companies to EDGAR filings by fuzzy name match, and a couple of enrichment steps fill in gaps (investor counts from Form D XML, missing website URLs, etc). The careers scraper does a diff-based sync against each company's ATS, so job history (first-seen dates) survives repeated rescrapes.

`web/lib/db.ts` is where the two feeds get assembled. The "Raised" tab unions four sources (accelerator+EDGAR, standalone EDGAR, TechCrunch-only, accelerator+TechCrunch-announced) into one ranked feed, and the "Hiring" tab is a separate query joining companies to job listings.

The frontend is a Next.js app (`web/`) that reads straight from the same Postgres database.

---

## Deployment

Runs automatically via GitHub Actions: a daily job (EDGAR, careers, hiring signals, funding news) plus a weekly Monday sweep that's split into steps so each one stays under the Action timeout. `main.py --mode weekly` runs the whole weekly sweep in one shot for local/manual use.

---

## Local setup

**Pipeline:**

```bash
uv sync
cp .env.example .env   # set DATABASE_URL (local dev Postgres) and PH_API_TOKEN

uv run python main.py --mode daily
uv run python main.py --mode weekly
uv run python validate.py

# Careers scraper:
uv run python scrapers/careers.py --hiring-sweep --workers 8
uv run python scrapers/yc_hiring.py   # reset YC isHiring companies for next careers sweep
```

**Frontend:**

```bash
cd web
npm install
npm run dev   # reads DATABASE_URL from ../.env
```

**Database:** set up a fresh Postgres DB with:

```bash
uv run python -c "from db.connection import apply_schema; apply_schema()"
uv run python db/migrate.py
```

`db/schema.sql` covers the original tables; everything since is in `db/migrate.py`, which runs all migrations in order and is safe to re-run against a partially-migrated DB.

## Promoting local data to production

`db/promote.py` copies newly-scraped rows straight from your local DB into production, so you can test a scraper change locally and ship the results without re-running it against prod. It's insert-only (`ON CONFLICT DO NOTHING`), so it's always safe to re-run. Set `PROD_DATABASE_URL` in `.env` alongside your local `DATABASE_URL`, then:

```bash
uv run python db/promote.py
```
