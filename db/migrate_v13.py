"""
Migration v13: add company_careers table for standalone/TC company careers data.

Accelerator companies store careers data in accelerator_companies.careers_ats/url.
TC-only and standalone EDGAR companies don't have accelerator_companies rows, so
we use this separate table keyed by normalized website URL.

Usage:
    uv run python db/migrate_v13.py
"""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS company_careers (
                    website TEXT PRIMARY KEY,
                    careers_ats TEXT,
                    careers_url TEXT,
                    careers_scraped_at TIMESTAMPTZ
                )
            """)
        conn.commit()
        print("Migration v13 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
