"""Create the baseline schema and apply every idempotent migration in order."""

from pathlib import Path

from db.connection import get_connection


BASE_SCHEMA = Path(__file__).with_name("schema.sql")


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
    (
        "v17: scraper completion state",
        """
        ALTER TABLE accelerator_companies
            ADD COLUMN IF NOT EXISTS cik_checked_at TIMESTAMPTZ;
        ALTER TABLE edgar_filings
            ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;
        """,
    ),
    (
        "v18: independent job type and level",
        r"""
        ALTER TABLE job_listings
            ADD COLUMN IF NOT EXISTS role_type TEXT,
            ADD COLUMN IF NOT EXISTS role_level TEXT;

        UPDATE job_listings
        SET role_type = CASE
                WHEN title ~* '\y(engineer|engineering|developer|software|backend|front.?end|full.?stack|data|ml|machine learning|artificial intelligence|infrastructure|devops|sre|site reliability|platform|security|qa|quality|hardware|embedded|firmware|scientist|cloud|mobile|ios|android|systems)\y'
                    THEN 'engineering'
                WHEN title ~* '\y(product manager|product lead|pm|product designer|ux|ui|user experience|user research|designer|design|researcher|research)\y'
                    THEN 'product'
                WHEN title ~* '\y(sales|account executive|ae|sdr|bdr|business development|marketing|growth|revenue|customer success|customer support|partnerships|solutions engineer|solutions consultant|demand generation|go.?to.?market|gtm|brand|content|communications|public relations|social media|community)\y'
                    THEN 'gtm'
                ELSE 'other'
            END,
            role_level = CASE
                WHEN title ~* '\y(intern|internship|co-?op|apprentice|apprenticeship)\y'
                    THEN 'intern'
                WHEN title ~* '\y(new.?grad|new graduate|recent grad|recent graduate|entry.?level|university grad|campus hire|junior|associate engineer|associate software|associate developer|associate data|associate product)\y'
                    THEN 'new_grad'
                ELSE 'experienced'
            END
        WHERE role_type IS NULL OR role_level IS NULL;

        ALTER TABLE job_listings
            ALTER COLUMN role_type SET DEFAULT 'other',
            ALTER COLUMN role_type SET NOT NULL,
            ALTER COLUMN role_level SET DEFAULT 'experienced',
            ALTER COLUMN role_level SET NOT NULL;
        """,
    ),
    (
        "v19: reconcile columns from the legacy baseline",
        """
        ALTER TABLE accelerator_companies
            ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE edgar_filings
            ADD COLUMN IF NOT EXISTS standalone_source TEXT,
            ADD COLUMN IF NOT EXISTS investor_count INT,
            ADD COLUMN IF NOT EXISTS vc_firm_signal TEXT;
        ALTER TABLE funding_news
            ADD COLUMN IF NOT EXISTS website TEXT;
        """,
    ),
    (
        "v20: remove confirmed false source links and valuation amounts",
        """
        UPDATE funding_news fn
        SET accelerator_id = NULL
        FROM accelerator_companies a
        WHERE a.id = fn.accelerator_id
          AND (fn.company_name, a.name) IN (
              ('Lion Energy Limited', 'Helion Energy'),
              ('Finly', 'Findly'),
              ('Coverwatch', 'Overwatch'),
              ('STRAAND', 'Strand AI'),
              ('Clove', 'Clover'),
              ('Penguin Solutions', 'Penguin AI'),
              ('Petra Labs', 'Pietra'),
              ('Capital Factory', 'Factory'),
              ('Gateway Capital Partners', 'Gateway'),
              ('Benchmark', 'Benchmark Labs'),
              ('AI Brief', 'Brief'),
              ('Ascent', 'Scent Lab'),
              ('Edgify', 'Edify'),
              ('Jedify', 'Edify'),
              ('Staked', 'Stacked'),
              ('Strala', 'Trala')
          );

        UPDATE accelerator_companies
        SET website = NULL, updated_at = NOW()
        WHERE (name, website) IN (
            ('Brief', 'https://dailyaibrief.com/'),
            ('Edify', 'https://jedify.com/'),
            ('Scent Lab', 'https://ascentfunding.com/'),
            ('Stacked', 'https://staked.us/'),
            ('Trala', 'https://strala.ai/')
        );

        UPDATE funding_news
        SET amount_usd = NULL
        WHERE source = 'techcrunch'
          AND company_name IN (
              'Nico',
              'Snabbit',
              'Upscale AI',
              'Elon Musk’s Boring Company',
              'Nuclear startup Valar Atomics in talks to'
          )
          AND article_title ~* 'valuation';
        """,
    ),
]


def run(url: str | None = None):
    conn = get_connection(url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('radar_schema_migrations'))")
            print("Applying baseline schema...")
            cur.execute(BASE_SCHEMA.read_text())
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS radar_schema_migrations (
                    version INT PRIMARY KEY,
                    label TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("SELECT version FROM radar_schema_migrations")
            applied = {row[0] for row in cur.fetchall()}
            applied_now = 0
            for label, ddl in STEPS:
                version = int(label.split(":", 1)[0].removeprefix("v"))
                if version in applied:
                    continue
                print(f"Applying {label}...")
                cur.execute(ddl)
                cur.execute(
                    "INSERT INTO radar_schema_migrations (version, label) VALUES (%s, %s)",
                    (version, label),
                )
                applied_now += 1
        conn.commit()
        print(f"Schema current. Applied {applied_now} migration(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
