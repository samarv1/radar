"""
Migration v2: introduce accelerator_companies, remove yc_companies + matches.

Run once against an existing database:
    uv run python db/migrate_v2.py
"""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection


DDL = """
-- New accelerator company registry
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

-- Link edgar_filings to accelerator_companies
ALTER TABLE edgar_filings
    ADD COLUMN IF NOT EXISTS accelerator_id INT REFERENCES accelerator_companies(id);

CREATE INDEX IF NOT EXISTS idx_accelerator_companies_cik ON accelerator_companies(edgar_cik)
    WHERE edgar_cik IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_edgar_filings_accelerator ON edgar_filings(accelerator_id)
    WHERE accelerator_id IS NOT NULL;
"""

DROP_OLD = """
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS yc_companies;
"""


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print("Applying new tables and columns...")
            cur.execute(DDL)
            print("Dropping old yc_companies and matches tables...")
            cur.execute(DROP_OLD)
        conn.commit()
        print("Migration v2 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
