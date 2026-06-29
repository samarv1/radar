"""
Migration v14: add offering_name column to edgar_filings.

This column was added to schema.sql but CREATE TABLE IF NOT EXISTS skips
column additions on existing tables, so existing DBs need this ALTER TABLE.

Usage:
    uv run python db/migrate_v14.py
"""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE edgar_filings ADD COLUMN IF NOT EXISTS offering_name TEXT"
            )
        conn.commit()
        print("Migration v14 complete: offering_name column added to edgar_filings.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
