"""
Migration v6: add posted_at to job_listings.

The table was created in v5 with only scraped_at; the scraper and feed query
both reference posted_at, which caused all inserts to fail.

Usage:
    uv run python db/migrate_v6.py
"""

import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE job_listings
                    ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ
            """)
        conn.commit()
        print("Migration v6 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
