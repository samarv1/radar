"""
Migration v8: add round_type to accelerator_companies.

Stores the enriched funding round label (Seed, Series A, Series B, etc.)
directly on the company record, as a fallback when no funding_news row exists.

Usage:
    uv run python db/migrate_v8.py
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
                    ADD COLUMN IF NOT EXISTS round_type TEXT
            """)
        conn.commit()
        print("Migration v8 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
