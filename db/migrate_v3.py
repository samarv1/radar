"""
Migration v3: add ph_launches table for Product Hunt enrichment.

Run once against an existing database:
    uv run python db/migrate_v3.py
"""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection

DDL = """
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
"""


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print("Creating ph_launches table...")
            cur.execute(DDL)
        conn.commit()
        print("Migration v3 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
