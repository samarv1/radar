"""
Migration v9: add company_status to accelerator_companies.

Stores the operational status of a company (Active, Inactive, Acquired, Public)
sourced from the YC Algolia API. NULL means unknown (non-YC companies or not yet fetched).

Usage:
    uv run python db/migrate_v9.py
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
                    ADD COLUMN IF NOT EXISTS company_status TEXT
            """)
        conn.commit()
        print("Migration v9 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
