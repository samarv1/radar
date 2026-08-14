"""
Manually set round_type for a company by name.

Manual one-off — not part of the automated pipeline (main.py).

Usage:
    uv run python -m scrapers.set_round_type "Blacksmith" "Series B"
    uv run python -m scrapers.set_round_type "Phonely" "Series A"
"""

import sys

from db.connection import get_connection


def set_round(name: str, round_type: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE accelerator_companies SET round_type = %s WHERE name ILIKE %s RETURNING id, name",
                (round_type, name),
            )
            rows = cur.fetchall()
            if not rows:
                print(f"No company found matching '{name}'")
                return
            for cid, cname in rows:
                print(f"Set '{cname}' (id={cid}) → {round_type}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: set_round_type.py <company_name> <round_type>")
        print('Example: set_round_type.py "Blacksmith" "Series B"')
        sys.exit(1)
    set_round(sys.argv[1], sys.argv[2])
