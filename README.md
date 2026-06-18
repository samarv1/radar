# Startup Sourcing Tool

A data pipeline that helps students find recently funded startups *before* they post jobs — then understand each company well enough to write a cold email that actually lands.

The core insight: the first 60–90 days after a startup closes a funding round is the best window to reach out. They have money and conviction, the founder still reads their own email, and the recruiting machine hasn't started yet. Most students miss this window entirely because they're browsing job boards, which are weeks or months behind.

---

## What It Does

The tool aggregates three free public signals into a single feed:

**1. SEC EDGAR Form D filings** — Any US company that raises venture capital must file a Form D with the SEC within 15 days of closing. This is fully public, completely free, and often surfaces deals weeks before they hit TechCrunch. We poll the EDGAR API daily and filter for US operating companies (excluding real estate funds and financial partnerships).

**2. Accelerator company directories** — We scrape YC, a16z, Sequoia, and Pear VC's public company directories to build a database of ~2,200 companies with known accelerator pedigree. These are companies that have already cleared a quality bar.

**3. Cross-reference** — The highest-value signal comes from combining the two above. A YC company that just filed a Form D = a quality-filtered startup with fresh capital. We fuzzy-match company names between the accelerator database and recent EDGAR filings to surface these intersections.

---

## Pipeline Architecture

```
EDGAR API ──────────────────────────────────────┐
                                                 ├──► cross_reference.py ──► matches table
YC / a16z / Sequoia / Pear scrapers ────────────┘
         │
         └──► cik_lookup.py ──► edgar_cik on accelerator_companies
```

All data lives in Postgres. `validate.py` checks data quality and acceptance criteria.

---

