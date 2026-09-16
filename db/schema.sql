CREATE TABLE IF NOT EXISTS accelerator_companies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    website TEXT,
    accelerator TEXT NOT NULL,
    batch TEXT,
    description TEXT,
    stage TEXT,
    tags TEXT[],
    source_url TEXT UNIQUE NOT NULL,
    edgar_cik TEXT,
    cik_confidence TEXT,
    jobs_url TEXT,
    is_excluded BOOLEAN NOT NULL DEFAULT FALSE,
    yc_is_hiring BOOLEAN NOT NULL DEFAULT FALSE,
    hq_city TEXT,
    hq_state TEXT,
    hq_country TEXT,
    location_tag TEXT,
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
    standalone_source TEXT,
    investor_count INT,
    vc_firm_signal TEXT,
    offering_name TEXT,
    city TEXT,
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
    round_type TEXT,
    article_title TEXT NOT NULL,
    article_url TEXT UNIQUE NOT NULL,
    published_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'techcrunch',
    accelerator_id INT REFERENCES accelerator_companies(id),
    website TEXT,
    industry TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_funding_news_accelerator ON funding_news(accelerator_id)
    WHERE accelerator_id IS NOT NULL;
