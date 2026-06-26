"""
Migration v11: add yc_is_hiring to accelerator_companies.

Stores the YC Algolia isHiring flag so companies appear on the hiring tab
even before a careers ATS is discovered.

Usage:
    uv run python db/migrate_v11.py
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
                    ADD COLUMN IF NOT EXISTS yc_is_hiring BOOLEAN NOT NULL DEFAULT FALSE
            """)
        conn.commit()
        print("Migration v11 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
