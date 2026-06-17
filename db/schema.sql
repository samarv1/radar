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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS yc_companies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    batch TEXT,
    description TEXT,
    website TEXT,
    tags TEXT[],
    yc_url TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    edgar_id INT REFERENCES edgar_filings(id) ON DELETE CASCADE,
    yc_id INT REFERENCES yc_companies(id) ON DELETE CASCADE,
    match_score NUMERIC NOT NULL,
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(edgar_id, yc_id)
);
