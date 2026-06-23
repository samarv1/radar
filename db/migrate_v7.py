"""
Migration v7: add first_seen_at to job_listings.

Enables delta-based scraping: instead of clear+re-insert, we diff the fresh
ATS response against existing rows. New job_ids get first_seen_at = NOW();
existing ones keep their original first_seen_at.

For BambooHR (which provides no posted_at), first_seen_at serves as the
effective "posted" proxy date for ranking and display.

Usage:
    uv run python db/migrate_v7.py
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
                    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ
            """)
        conn.commit()
        print("Migration v7 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
