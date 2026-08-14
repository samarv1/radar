"""
Runs all migrations (v2-v16) against the database in order.

All migrations use `IF NOT EXISTS`-style DDL (or, for v12, a data-fix `UPDATE`
that's a no-op on an empty table), so this is safe to run start-to-finish
against a brand-new database, or to re-run against one that's already
partially migrated.

Usage:
    uv run python -c "from db.connection import apply_schema; apply_schema()"
    uv run python -m db.migrate
"""


from db.connection import get_connection


STEPS = [
    (
        "v2: accelerator_companies table, drop yc_companies + matches",
        """
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
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        ALTER TABLE edgar_filings
            ADD COLUMN IF NOT EXISTS accelerator_id INT REFERENCES accelerator_companies(id);

        CREATE INDEX IF NOT EXISTS idx_accelerator_companies_cik ON accelerator_companies(edgar_cik)
            WHERE edgar_cik IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_edgar_filings_accelerator ON edgar_filings(accelerator_id)
            WHERE accelerator_id IS NOT NULL;

        DROP TABLE IF EXISTS matches;
        DROP TABLE IF EXISTS yc_companies;
        """,
    ),
    (
        "v3: ph_launches table",
        """
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
        """,
    ),
    (
        "v4: funding_news table",
        """
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
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_funding_news_accelerator ON funding_news(accelerator_id)
            WHERE accelerator_id IS NOT NULL;
        """,
    ),
    (
        "v5: careers scraping support (accelerator_companies columns, job_listings table)",
        """
        ALTER TABLE accelerator_companies
            ADD COLUMN IF NOT EXISTS careers_ats TEXT,
            ADD COLUMN IF NOT EXISTS careers_url TEXT,
            ADD COLUMN IF NOT EXISTS careers_scraped_at TIMESTAMPTZ;

        CREATE TABLE IF NOT EXISTS job_listings (
            id SERIAL PRIMARY KEY,
            company_id INT NOT NULL REFERENCES accelerator_companies(id),
            ats TEXT NOT NULL,
            job_id TEXT,
            title TEXT NOT NULL,
            department TEXT,
            location TEXT,
            category TEXT NOT NULL,
            job_url TEXT,
            scraped_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, ats, job_id)
        );

        CREATE INDEX IF NOT EXISTS idx_job_listings_company
            ON job_listings(company_id);
        """,
    ),
    (
        "v6: job_listings.posted_at",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ",
    ),
    (
        "v7: job_listings.first_seen_at",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ",
    ),
    (
        "v8: accelerator_companies.round_type",
        "ALTER TABLE accelerator_companies ADD COLUMN IF NOT EXISTS round_type TEXT",
    ),
    (
        "v9: accelerator_companies.company_status",
        "ALTER TABLE accelerator_companies ADD COLUMN IF NOT EXISTS company_status TEXT",
    ),
    (
        "v10: edgar_filings.offering_name",
        "ALTER TABLE edgar_filings ADD COLUMN IF NOT EXISTS offering_name TEXT",
    ),
    (
        "v11: accelerator_companies.yc_is_hiring",
        """
        ALTER TABLE accelerator_companies
            ADD COLUMN IF NOT EXISTS yc_is_hiring BOOLEAN NOT NULL DEFAULT FALSE
        """,
    ),
    (
        "v12: data fix - strip leading dollar amounts from TC-derived company names",
        r"""
        UPDATE funding_news
        SET company_name = regexp_replace(company_name, E'^\$[\d.,]+\s*[BMKbmk]?\s+', '', 'i')
        WHERE company_name ~ E'^\$[\d.,]+\s*[BMKbmk]?\s+\w'
        """,
    ),
    (
        "v13: company_careers table",
        """
        CREATE TABLE IF NOT EXISTS company_careers (
            website TEXT PRIMARY KEY,
            careers_ats TEXT,
            careers_url TEXT,
            careers_scraped_at TIMESTAMPTZ
        )
        """,
    ),
    (
        "v14: edgar_filings.offering_name (idempotent re-add, no-op if v10 already ran)",
        "ALTER TABLE edgar_filings ADD COLUMN IF NOT EXISTS offering_name TEXT",
    ),
    (
        "v15: funding_news.industry",
        "ALTER TABLE funding_news ADD COLUMN IF NOT EXISTS industry TEXT",
    ),
    (
        "v16: HQ location tag columns",
        """
        ALTER TABLE edgar_filings ADD COLUMN IF NOT EXISTS city TEXT;
        ALTER TABLE accelerator_companies ADD COLUMN IF NOT EXISTS hq_city TEXT;
        ALTER TABLE accelerator_companies ADD COLUMN IF NOT EXISTS hq_state TEXT;
        ALTER TABLE accelerator_companies ADD COLUMN IF NOT EXISTS hq_country TEXT;
        ALTER TABLE accelerator_companies ADD COLUMN IF NOT EXISTS location_tag TEXT;
        """,
    ),
]


def run(url: str | None = None):
    conn = get_connection(url)
    try:
        with conn.cursor() as cur:
            for label, ddl in STEPS:
                print(f"Applying {label}...")
                cur.execute(ddl)
        conn.commit()
        print(f"All {len(STEPS)} migrations complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
