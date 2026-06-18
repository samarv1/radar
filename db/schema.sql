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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_accelerator_companies_cik ON accelerator_companies(edgar_cik)
    WHERE edgar_cik IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_edgar_filings_accelerator ON edgar_filings(accelerator_id)
    WHERE accelerator_id IS NOT NULL;
