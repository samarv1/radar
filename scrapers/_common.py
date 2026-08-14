"""
Shared helpers for the directory scrapers (lightspeed, pear, sequoia,
techstars, a16z, ...): the "fetch a list, upsert each row into
accelerator_companies, report counts" shape they all repeat.
"""

from db.connection import get_connection

DEFAULT_HEADERS = {"User-Agent": "radar-tool contact@example.com"}


def execute_upsert(conn, sql: str, params: dict) -> bool:
    """Run an upsert whose query ends in `RETURNING (xmax = 0) AS inserted`
    and return whether the row was newly inserted (False means updated)."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        result = cur.fetchone()
        return result[0] if result else False


def run_upsert_batch(rows, upsert_fn, conn=None) -> tuple[int, int]:
    """
    Upsert `rows` one at a time via `upsert_fn(conn, row) -> bool`, managing
    the connection lifecycle (commit + close) and counting inserted vs.
    updated. Pass an existing `conn` to reuse it instead of opening a new one
    (e.g. so a caller can batch several scrapers on one connection).
    """
    owns_conn = conn is None
    conn = conn or get_connection()
    inserted = updated = 0
    try:
        for row in rows:
            if upsert_fn(conn, row):
                inserted += 1
            else:
                updated += 1
        conn.commit()
    finally:
        if owns_conn:
            conn.close()
    return inserted, updated
