# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **startup sourcing tool for students** — helping college students and recent grads find recently funded startups *before* they post jobs, then understand each company's needs to write targeted cold emails.

The full product spec lives in `startup_sourcing_tool_spec.md`. Read it before making architectural decisions.

## Planned Tech Stack

- **Frontend:** Next.js
- **Backend/Scrapers:** Python
- **Database:** Postgres (SQLite acceptable for early MVP)
- **Hosting:** Railway or Render

## Build Phases

Development is intentionally sequential — validate data quality at each phase before proceeding:

1. **Phase 1 (Core Pipeline):** SEC EDGAR Form D scraper → YC directory scraper → cross-reference the two
2. **Phase 2 (Enrichment):** Careers page scraping + a16z newsletter RSS ingestion
3. **Phase 3 (Twitter Enrichment):** Founder Twitter timelines via TwitterAPI.io or SociaVault
4. **Phase 4 (UI):** Only after Phases 1–3 are manually validated

## Data Sources

| Source | API/Method | Cost |
|--------|-----------|------|
| SEC EDGAR Form D | EDGAR full-text search API | Free |
| YC directory | Scrape `ycombinator.com/companies` | Free |
| a16z Build newsletter | RSS feed (`a16zbuild.substack.com/feed`) | Free |
| Careers pages | HTTP requests to `company.com/careers`, `/jobs`, `/join` | Free |
| Twitter timelines | TwitterAPI.io ($0.15/1k tweets) or SociaVault (50 free credits) | ~$5–20/mo |

**Rejected sources:** Crunchbase API (~$500–800/mo), LinkedIn (lags, legally grey for scraping), Twitter for discovery (inconsistent cadence), traditional job boards.

## Key Product Decisions

- **No matching algorithm in MVP** — students browse and self-select fit; liberal on discovery (show more, not fewer companies)
- **No job board** — students are reaching out *before* roles are posted
- **ATS detection:** Greenhouse (`boards.greenhouse.io`), Lever (`jobs.lever.co`), Ashby (`jobs.ashbyhq.com`)
- **Access control:** Password-protect the site, share only within a trusted org initially (e.g. AgieWorks); keep the password out of code/commits
- **Email finding:** Don't build email lookup; surface founder Twitter/LinkedIn and direct users to Apollo
- **Ideal target profile:** Funded within 90 days, Seed/Series A, 2–15 employees, 0–5 open roles, founder active on Twitter

## The Core High-Signal Query

The highest-value target = YC company that filed an SEC Form D within the last 90 days. Cross-referencing these two free public datasets produces signal that neither gives alone. Fuzzy match company names between the two sources (names are often inconsistent).

## EDGAR Filtering Rules

When polling EDGAR Form D filings, filter to:
- Filed within last 90 days
- US companies
- Exclude real estate partnerships and funds
