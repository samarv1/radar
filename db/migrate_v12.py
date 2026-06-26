"""
Migration v12: fix company names in funding_news that were scraped with a
leading dollar amount (e.g. "$2.5B Cerebras" → "Cerebras").

This happens when a TC article title starts with the amount before the company
name, and parse_company splits on "raises" leaving "$2.5B Cerebras" as the name.

Usage:
    uv run python db/migrate_v12.py
"""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from db.connection import get_connection


def run():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE funding_news
                SET company_name = regexp_replace(company_name, E'^\\$[\\d.,]+\\s*[BMKbmk]?\\s+', '', 'i')
                WHERE company_name ~ E'^\\$[\\d.,]+\\s*[BMKbmk]?\\s+\\w'
            """)
            count = cur.rowcount
        conn.commit()
        print(f"Migration v12 complete. Fixed {count} company name(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
