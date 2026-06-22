"""
Migration v5: careers scraping support.

Adds careers_ats, careers_url, careers_scraped_at to accelerator_companies,
and creates the job_listings table.

Usage:
    uv run python db/migrate_v5.py
"""

import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE accelerator_companies
                    ADD COLUMN IF NOT EXISTS careers_ats TEXT,
                    ADD COLUMN IF NOT EXISTS careers_url TEXT,
                    ADD COLUMN IF NOT EXISTS careers_scraped_at TIMESTAMPTZ
            """)

            cur.execute("""
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
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_job_listings_company
                    ON job_listings(company_id)
            """)

        conn.commit()
        print("Migration v5 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
