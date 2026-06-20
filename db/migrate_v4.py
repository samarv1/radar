"""
Migration v4: add funding_news table for TechCrunch and future funding signal sources.

    uv run python db/migrate_v4.py
"""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

DDL = """
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
"""

def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
        print("Migration v4 complete.")
    finally:
        conn.close()

if __name__ == "__main__":
    run()
