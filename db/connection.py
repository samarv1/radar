import os
import re
import psycopg2
from dotenv import load_dotenv

load_dotenv()

_logged_hosts = set()


def _log_target(url: str):
    """Print the DB host once per process so it's always clear which
    database (local dev vs. PROD_DATABASE_URL) a run is actually hitting."""
    match = re.search(r"@([^/:]+)", url)
    host = match.group(1) if match else "localhost"
    if host not in _logged_hosts:
        _logged_hosts.add(host)
        print(f"[db] connecting to {host}")


def get_connection(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in environment")
    _log_target(url)
    return psycopg2.connect(url)


def apply_schema(url: str | None = None):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        sql = f.read()
    conn = get_connection(url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()
