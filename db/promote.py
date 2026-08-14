"""
Copies newly scraped rows from the local database into production, without
re-running scrapers (which are slow because of the external API calls, not
the DB writes).

accelerator_companies.id is a SERIAL and local's id for a company has no
relationship to production's id for the same company, so rows can't just be
copied as-is — every table that references accelerator_companies.id would
end up pointing at the wrong row (or nothing) in production. Instead:
  1. accelerator_companies is promoted first, matched/deduped on source_url,
     producing a {local_id: prod_id} map (covering both newly-inserted and
     already-existing companies).
  2. Every child table's FK column is remapped through that map before being
     upserted into production, matched on that table's own unique constraint.

Inserts use ON CONFLICT ... DO NOTHING everywhere — this never overwrites a
row already in production, so it's always safe to run again.

Usage:
    uv run python -m db.promote
"""

import os

from db.connection import get_connection, apply_schema
from db.migrate import run as apply_migrations


SOURCE_URL = os.environ.get("DATABASE_URL")
TARGET_URL = os.environ.get("PROD_DATABASE_URL")

# Columns never copied directly: id is a SERIAL (target assigns its own),
# created_at/updated_at are left to the target's own defaults.
SKIP_COLUMNS = {"id", "created_at", "updated_at"}

CHILD_TABLES = [
    ("edgar_filings", ["accession_number"], "accelerator_id"),
    ("ph_launches", ["ph_id"], "accelerator_id"),
    ("funding_news", ["article_url"], "accelerator_id"),
    ("job_listings", ["company_id", "ats", "job_id"], "company_id"),
]


def get_table_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def shared_columns(src_conn, tgt_conn, table):
    src_cols = get_table_columns(src_conn, table)
    tgt_cols = set(get_table_columns(tgt_conn, table))
    return [c for c in src_cols if c in tgt_cols and c not in SKIP_COLUMNS]


def remap_fk(id_map, local_id):
    if local_id is None:
        return None
    return id_map.get(local_id)


def promote_accelerator_companies(src_conn, tgt_conn):
    table = "accelerator_companies"
    cols = shared_columns(src_conn, tgt_conn, table)
    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))

    with src_conn.cursor() as cur:
        cur.execute(f"SELECT id, {col_list} FROM {table}")
        rows = cur.fetchall()

    # +1 for leading id column
    source_url_idx = cols.index("source_url") + 1
    local_id_by_source_url = {row[source_url_idx]: row[0] for row in rows}

    inserted = 0
    with tgt_conn.cursor() as cur:
        for row in rows:
            values = row[1:]
            cur.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT (source_url) DO NOTHING",
                values,
            )
            inserted += cur.rowcount

        source_urls = list(local_id_by_source_url.keys())
        cur.execute(
            f"SELECT source_url, id FROM {table} WHERE source_url = ANY(%s)",
            (source_urls,),
        )
        prod_id_by_source_url = dict(cur.fetchall())

    id_map = {
        local_id: prod_id_by_source_url[source_url]
        for source_url, local_id in local_id_by_source_url.items()
        if source_url in prod_id_by_source_url
    }

    return id_map, inserted, len(rows)


def promote_child_table(src_conn, tgt_conn, table, unique_cols, fk_column, id_map):
    cols = shared_columns(src_conn, tgt_conn, table)
    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    conflict_cols = ", ".join(unique_cols)
    fk_idx = cols.index(fk_column)

    with src_conn.cursor() as cur:
        cur.execute(f"SELECT {col_list} FROM {table}")
        rows = cur.fetchall()

    inserted = 0
    skipped_no_parent = 0
    with tgt_conn.cursor() as cur:
        for row in rows:
            local_fk = row[fk_idx]
            if local_fk is not None and remap_fk(id_map, local_fk) is None:
                # Parent company wasn't promoted (shouldn't normally happen
                # since accelerator_companies is promoted first) — skip
                # rather than insert a dangling/wrong FK.
                skipped_no_parent += 1
                continue
            values = list(row)
            values[fk_idx] = remap_fk(id_map, local_fk)
            cur.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_cols}) DO NOTHING",
                values,
            )
            inserted += cur.rowcount

    return inserted, len(rows), skipped_no_parent


def promote_company_careers(src_conn, tgt_conn):
    table = "company_careers"
    cols = shared_columns(src_conn, tgt_conn, table)
    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))

    with src_conn.cursor() as cur:
        cur.execute(f"SELECT {col_list} FROM {table}")
        rows = cur.fetchall()

    inserted = 0
    with tgt_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT (website) DO NOTHING",
                row,
            )
            inserted += cur.rowcount

    return inserted, len(rows)


def run():
    if not SOURCE_URL:
        raise RuntimeError("DATABASE_URL not set in environment")
    if not TARGET_URL:
        raise RuntimeError("PROD_DATABASE_URL not set in environment")
    if SOURCE_URL == TARGET_URL:
        raise RuntimeError(
            "DATABASE_URL and PROD_DATABASE_URL are identical — refusing to run "
            "(check your .env)"
        )

    src_conn = get_connection(SOURCE_URL)
    tgt_conn = get_connection(TARGET_URL)
    tgt_conn.autocommit = False

    summary = []
    try:
        apply_schema(TARGET_URL)
        apply_migrations(TARGET_URL)

        id_map, inserted, total = promote_accelerator_companies(src_conn, tgt_conn)
        summary.append(("accelerator_companies", inserted, total - inserted, total))

        for table, unique_cols, fk_column in CHILD_TABLES:
            inserted, total, skipped_no_parent = promote_child_table(
                src_conn, tgt_conn, table, unique_cols, fk_column, id_map
            )
            skipped = total - inserted
            summary.append((table, inserted, skipped, total))
            if skipped_no_parent:
                print(
                    f"  warning: {skipped_no_parent} row(s) in {table} skipped "
                    f"(parent company not found in production)"
                )

        inserted, total = promote_company_careers(src_conn, tgt_conn)
        summary.append(("company_careers", inserted, total - inserted, total))

        tgt_conn.commit()
    except Exception:
        tgt_conn.rollback()
        raise
    finally:
        src_conn.close()
        tgt_conn.close()

    print(f"\n{'table':<22} {'inserted':>10} {'skipped':>10} {'total':>10}")
    for table, inserted, skipped, total in summary:
        print(f"{table:<22} {inserted:>10} {skipped:>10} {total:>10}")


if __name__ == "__main__":
    run()
