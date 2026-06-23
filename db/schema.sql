CREATE TABLE IF NOT EXISTS accelerator_companies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    website TEXT,
    accelerator TEXT NOT NULL,       -- 'yc', 'pear', 'sequoia', 'a16z'
    batch TEXT,                      -- YC batch (e.g. 'W24') or first-partnered year for others
    description TEXT,
    stage TEXT,                      -- 'Pre-Seed/Seed', 'Early', 'Growth', 'IPO', 'Acquired'
    tags TEXT[],
    source_url TEXT UNIQUE NOT NULL, -- canonical URL on the accelerator's site
    edgar_cik TEXT,                  -- NULL until CIK lookup runs
    cik_confidence TEXT,             -- 'exact', 'fuzzy', or NULL
    jobs_url TEXT,                   -- careers page if known (Pear provides this)
    is_excluded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS edgar_filings (
    id SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    state TEXT,
    date_filed DATE,
    date_of_first_sale DATE,
    amount_raised NUMERIC,
    industry_group TEXT,
    entity_type TEXT,
    accession_number TEXT UNIQUE NOT NULL,
    raw_url TEXT,
    accelerator_id INT REFERENCES accelerator_companies(id),
    standalone_source TEXT,              -- 'techcrunch' or 'producthunt' for non-accelerator validated startups
    investor_count INT,                  -- totalNumberAlreadyInvested from Form D XML
    vc_firm_signal TEXT,                 -- VC firm name if found in director/promoter relationship clarifications
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_accelerator_companies_cik ON accelerator_companies(edgar_cik)
    WHERE edgar_cik IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_edgar_filings_accelerator ON edgar_filings(accelerator_id)
    WHERE accelerator_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS ph_launches (
    id SERIAL PRIMARY KEY,
    ph_id TEXT UNIQUE NOT NULL,
    product_name TEXT NOT NULL,
    tagline TEXT,
    ph_url TEXT,
    website TEXT,
    votes_count INT,
    launched_at TIMESTAMPTZ,
    maker_name TEXT,
    maker_twitter TEXT,
    accelerator_id INT REFERENCES accelerator_companies(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ph_launches_accelerator ON ph_launches(accelerator_id)
    WHERE accelerator_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS funding_news (
    id SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    amount_usd NUMERIC,
    round_type TEXT,                 -- 'Seed', 'Series A', etc.
    article_title TEXT NOT NULL,
    article_url TEXT UNIQUE NOT NULL,
    published_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'techcrunch',
    accelerator_id INT REFERENCES accelerator_companies(id),
    website TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_funding_news_accelerator ON funding_news(accelerator_id)
    WHERE accelerator_id IS NOT NULL;
