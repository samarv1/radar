"""
Migration v10: add offering_name to edgar_filings.

Stores the nameOfOffering field from Form D XML (e.g. "Series A Preferred Stock").
Used by enrich_edgar.py to extract and by enrich_round_type.py as a fallback
round type source.

Usage:
    uv run python db/migrate_v10.py
"""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE edgar_filings
                    ADD COLUMN IF NOT EXISTS offering_name TEXT
            """)
        conn.commit()
        print("Migration v10 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
