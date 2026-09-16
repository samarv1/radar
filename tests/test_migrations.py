import os

import psycopg2
import pytest

from db.migrate import run


@pytest.mark.integration
def test_migration_runner_builds_current_schema():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")

    run(url)
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('accelerator_companies', 'edgar_filings', 'job_listings')
            """
        )
        columns = set(cur.fetchall())

    assert ("accelerator_companies", "cik_checked_at") in columns
    assert ("edgar_filings", "enriched_at") in columns
    assert ("job_listings", "role_type") in columns
    assert ("job_listings", "role_level") in columns

    run(url)
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM radar_schema_migrations")
        assert cur.fetchone()[0] > 0
