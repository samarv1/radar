# Startup Sourcing Tool — Product Spec & Build Guide

## Overview

A tool that helps students find recently funded startups before they post jobs, understand the company's current needs, and identify the best angle to reach out with a cold email. The core insight is that students don't need a job board — they need to get in front of founders before the hiring machine spins up.

**Target user:** College students and recent grads trying to break into early-stage startups via proactive cold outreach.

**Core value prop:** Find funded startups before they post jobs, and understand exactly what they need so you can position yourself as the answer.

---

## The Problem

Students trying to recruit into startups face three compounding problems:

1. **Discovery is manual and slow** — finding recently funded startups requires checking Crunchbase, TechCrunch, Twitter, YC, and LinkedIn separately with no unified feed
2. **They arrive too late** — by the time a startup posts on LinkedIn or a job board, hundreds of applicants have already applied
3. **They don't know their angle** — even when they find a good company, students don't know whether to pitch themselves as an engineer, a PM, a growth hire, or something else

Existing tools like Harmonic.ai solve parts of this but are priced for VC firms (~$25,000/year minimum). Students are completely unserved.

---

## Key Insights From Research

### The Funding Window
The first 60-90 days post-funding announcement is the highest-value outreach window. The startup has money, conviction, and is actively thinking about team-building — but hasn't built a recruiting machine yet. A cold email from a student can still reach the founder directly.

### The YC + Post-Funding Intersection
A YC company that raises a seed round 3-6 months after their batch ends is the single best target profile:
- Quality filter already applied (YC acceptance)
- Fresh capital deployed
- Small enough that founders still read their own email
- Past the chaotic early days but not yet corporate

### Students Don't Know What They Want
Unlike recruiters searching for a specific role, students often have overlapping skills (e.g. product + engineering) and are open to multiple functions. The tool should surface opportunities and let students self-identify their fit rather than filtering upfront.

### Liberal > Conservative on Discovery
Show students more companies, not fewer. Algorithmic matching can come later. Students are better at evaluating their own fit than any MVP matching system will be. The tool's job is to surface the signal — the student decides if they fit.

### The Signal Stack (from Ben Lang / Harmonic research)
Three distinct signals matter, each telling you something different:
- **Follower growth** — who's getting attention and buzz
- **Hiring velocity** — who's actively deploying capital into headcount
- **Active job postings** — who has confirmed open roles right now

The ideal target scores on all three. A student finding a company with high follower growth + recent funding + 1-2 open roles is in the perfect window — before the flood of applicants arrives.

---

## Data Sources

### Primary Discovery Sources

#### 1. SEC EDGAR Form D Filings
- **What it is:** All US companies that raise capital must file a Form D within 15 days of closing
- **Why it's valuable:** Catches deals before press coverage, often weeks earlier. Fully public and free.
- **Cadence:** Continuous — new filings every day
- **Coverage:** Broadest possible — every US fundraise regardless of press coverage
- **How to use:** Poll the EDGAR full-text search API for new Form D filings, filter by date and industry codes
- **Limitations:** Dry data — no company description, requires enrichment to be useful

#### 2. YC Directory + SEC EDGAR Cross-Reference
- **What it is:** YC's public directory of all companies from every batch, cross-referenced with Form D filings
- **Why it's valuable:** YC is already a quality filter. Combining YC pedigree with fresh post-batch funding produces the highest-quality target list possible
- **Cadence:** YC directory is scraped after each batch demo day (twice yearly for new batches, but ongoing for post-batch fundraises). EDGAR cross-reference runs continuously.
- **Coverage:** YC companies only — smaller universe but much higher signal
- **How to use:** Scrape YC directory for all companies + graduation dates, then match company names against recent EDGAR Form D filings
- **Why this is the secret weapon:** You're combining two free public datasets to produce something neither gives you alone

#### 3. a16z Build Newsletter
- **What it is:** Weekly newsletter from a16z curating startups with open roles, including founder Twitter handles, funding context, and what they're building
- **Why it's valuable:** A16z has already done quality filtering. Featured companies have implicit VC endorsement. Data is already semi-structured (company, founder handle, funding stage, what they're building).
- **Cadence:** Weekly, consistent
- **Coverage:** Curated subset — smaller but very high quality
- **How to use:** Subscribe RSS feed at `a16zbuild.substack.com/feed`, run a cron job weekly to detect new issues, parse and extract company mentions automatically
- **Limitations:** Only covers companies a16z finds interesting — skews toward certain sectors

### Considered and Rejected Sources

#### Crunchbase API
- Comprehensive and well-structured but costs ~$500-800/month
- Better used as enrichment fallback than primary discovery
- **Decision:** Skip for MVP, revisit if pipeline has coverage gaps

#### Twitter/X for Discovery
- High-signal accounts like @benln post curated startup hiring lists
- **Problem 1:** Inconsistent cadence — you can't build a pipeline around when someone decides to tweet
- **Problem 2:** Sourcing and maintaining a list of 20-30 high-signal accounts is itself a manual research project
- **Problem 3:** The signal is already downstream — Ben Lang pulls from Harmonic, so you'd be scraping a scrape
- **Decision:** Not used for discovery. Used for enrichment only (see below).

#### LinkedIn
- Lags by weeks for startup hiring signals
- Founders update profiles slowly
- **Decision:** Skip entirely for MVP

#### Traditional Job Boards (Indeed, LinkedIn Jobs)
- Most early-stage startups don't post here at all
- By the time a role appears, competition is high
- **Decision:** Skip. Students using this tool are reaching out *before* jobs are posted.

---

## Enrichment Layer

Once a startup is identified via discovery, enrich it with the following:

### Careers Page Scraping
- **What:** Check if company has a `/careers` page, detect which ATS they use (Greenhouse, Lever, Ashby detectable from URL patterns), count and loosely categorize open roles
- **Why:** Confirms they're in hiring mode. Role categories (eng, product, GTM, ops) tell the student what gaps exist and which angle to pitch.
- **How:** Simple HTTP request to `company.com/careers`, check for Greenhouse/Lever/Ashby URL patterns
- **Note:** Many early-stage startups have no careers page at all — that's a signal too. It means they're pre-hiring-infrastructure and a cold email is even more likely to land.

### Founder Twitter Timeline
- **What:** Pull the founder's recent tweets (last 30-60 days)
- **Why:** Gives students genuine personalization material. A cold email that references something the founder actually said stands out immediately. Also reveals founder communication style, what problems they're obsessing over, and what kind of person they are.
- **How:** Use TwitterAPI.io ($0.15/1,000 tweets, pay-as-you-go) or SociaVault (50 free credits to start). Pull by Twitter handle — often available from a16z newsletter directly.
- **What to surface:** Recent topics, any hiring-related posts, tone and communication style

### Team Composition Signal
- **What:** Founding team backgrounds, current headcount estimate
- **Why:** Tells the student what's missing. Engineering-heavy founding team with no marketing = lead with growth. All business people = lead with technical skills.
- **How:** LinkedIn scraping is legally grey. Use what's available from YC directory, company website, and press coverage instead.

### Investor Names
- **What:** Who led the round, notable angels
- **Why:** A16z-backed vs bootstrapped signals trajectory, culture, and growth expectations. Also useful personalization material.
- **How:** Already captured in EDGAR Form D and press coverage

---

## Signal Framework

Each startup in the feed should display a lightweight signal summary so students can quickly evaluate opportunity:

| Signal | What It Means | Source |
|--------|--------------|--------|
| Days since funding | Freshness of opportunity window | EDGAR / news |
| Round size + stage | How much runway, how aggressive growth will be | EDGAR |
| Investor names | Trajectory and legitimacy signal | EDGAR / press |
| Headcount | How early-stage they really are | LinkedIn / website |
| Open role count + categories | What gaps exist on the team | Careers page |
| Founder Twitter active? | Reachability and personalization potential | Twitter |

**Ideal target profile for a student:**
- Funded within last 90 days
- Seed or Series A (small enough to reach founder directly)
- 2-15 employees
- 0-5 open roles (hiring but not yet systematic)
- Founder active on Twitter

---

## What This Is NOT

- Not a job board — students are not applying to posted roles
- Not a matching algorithm — students decide their own fit
- Not a recruiter tool — enrichment is for personal positioning, not pipeline management
- Not competing with Harmonic — Harmonic serves VCs at $25k/year, this serves students for free or nearly free

---

## Competitive Landscape

**Harmonic.ai** — closest to what we're building on the data side. Tracks startup growth signals (follower growth, hiring velocity, headcount). Priced at $25,000/year minimum, built for VC firms. Their data powers Ben Lang's Twitter posts about fastest-growing startups. We cannot use their API affordably.

**Crunchbase** — comprehensive but expensive API, lagging data, built for investors and sales teams.

**Wellfound (AngelList Talent)** — startup job board but students are responding to posted roles, not getting ahead of them.

**LinkedIn** — noisy, slow, dominated by large companies.

**Gap we're filling:** Nobody is aggregating early startup signals specifically for students trying to do proactive cold outreach. The people who know how to do this (like Ben Lang) do it manually. We're automating what they do manually and making it accessible.

---

## MVP Build Plan

### Guiding principle
Validate data quality before building any UI. Bad data in a polished product is worse than good data in a spreadsheet. Use yourself and a handful of student friends as guinea pigs first.

### Phase 1 — Core Pipeline (Weeks 1-2)

**Goal:** Get a working list of recently funded startups into a database

**Step 1: SEC EDGAR Form D scraper**
- Poll EDGAR full-text search API for new Form D filings
- Filter by: filed within last 90 days, US companies, exclude real estate and funds
- Extract: company name, state, date of filing, amount raised, industry
- Store in simple SQLite or Postgres table

**Step 2: YC directory scraper**
- Scrape `ycombinator.com/companies` for full company list
- Extract: company name, batch, one-liner description, website URL
- Store locally

**Step 3: YC + EDGAR cross-reference**
- Match company names between YC directory and recent EDGAR filings
- Fuzzy match on company name (company names are inconsistent across sources)
- Flag matches as high-priority targets
- This intersection is your highest-quality signal

**Pipeline check:** Before moving on, manually inspect a sample of the output. Do the companies look real and relevant? Are the YC cross-references matching correctly? Fix any data quality issues before wiring into the next step.

### Phase 2 — Enrichment Pipeline (Weeks 3-4)

**Goal:** Add enough context to each company that a student can evaluate it

**Step 4: Careers page detection**
- For each company, hit `company.com/careers`, `/jobs`, `/join`
- Detect Greenhouse (`boards.greenhouse.io`), Lever (`jobs.lever.co`), Ashby (`jobs.ashbyhq.com`) from URL patterns
- Count open roles, extract job titles, loosely categorize (eng / product / GTM / ops / other)
- Store role count and categories

**Step 5: a16z newsletter RSS ingestion**
- Subscribe to `a16zbuild.substack.com/feed`
- Set up weekly cron job to check for new issues
- Parse new issues, extract company mentions, founder Twitter handles, descriptions
- Add to database, flag as a16z-featured

**Pipeline check:** Spot check 10-20 enriched profiles. Does each one have enough context to understand what the company does, where they are in their growth, and what roles might be open? If the enrichment feels thin or inaccurate, fix it before adding more data sources.

### Phase 3 — Twitter Enrichment (Week 5)

**Goal:** Add founder voice and personalization material

**Step 6: Founder Twitter timeline pull**
- For companies with known founder Twitter handles (from a16z newsletter or manual research)
- Use TwitterAPI.io or SociaVault free tier
- Pull last 30 days of tweets
- Store raw and surface most recent 5-10 tweets on company profile

**Pipeline check:** Look at the raw Twitter data being pulled for a handful of founders. Is it surfacing useful, recent content? Is the signal actually adding personalization value or just noise? Tune before moving to UI.

### Phase 4 — UI (Week 6+)

**Only build this after Phases 1-3 are validated by the founder.**

This section describes the minimum viable interface. The UI can and should be expanded significantly once data quality is confirmed and the tool is in the hands of real users. Do not over-invest in UI before that point.

**Minimum viable interface:**
- Feed of recently funded startups, sorted by recency
- Each card shows: company name, one-liner, round size, days since funding, open role count
- Click through to full enrichment view: team composition, investor names, open roles by category, founder Twitter snippets
- No matching algorithm, no filtering by role — students browse and self-select

**Stack suggestion:** Next.js frontend, Python backend for scrapers, Postgres for storage. Keep it simple.

---

## Cost to Run MVP

| Source | Cost |
|--------|------|
| SEC EDGAR | Free |
| YC directory scraping | Free |
| a16z newsletter RSS | Free |
| Careers page scraping | Free |
| TwitterAPI.io (enrichment only, spot checks) | ~$5-20/month at scale |
| Hosting (Railway, Render, or similar) | ~$10-20/month |
| **Total** | **~$15-40/month** |

This is essentially free to validate. No reason to spend money until you have confirmed the data quality is good and students find it useful.

---

## Open Questions / Future Decisions

- **Email finding:** Rather than building email lookup into the MVP, redirect users to the founder's LinkedIn profile and recommend Apollo for email finding. Where contact information is already available from our data sources (e.g. Twitter handle, LinkedIn URL from a16z newsletter), surface that directly on the company profile.
- **Sector filtering:** Should students be able to filter by sector (AI, fintech, biotech)? Probably yes but not for MVP — let them browse first.
- **Access control:** No public launch initially. Password protect the site and share only within a trusted org (e.g. AgieWorks) to control early access and gather quality feedback before opening up. Implement password protection as part of the Phase 4 UI build — keep the password out of this spec and set it separately at build time. Monetization is not a priority right now.
- **Matching algorithm:** Future version could take student background as input and suggest angle. Not for MVP — too much technical complexity for unvalidated use case.
- **Additional newsletters:** Next Play, Early Days Substack, Harmonic Hot 25 (public version) could be added as sources after a16z is working.
