#!/usr/bin/env bash
# Run this before every deployment: ./precheck.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WEB="$ROOT/web"
PASS=0
FAIL=0
WARN=0

ok()   { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN + 1)); }

# ─── 1. Secrets not in git ───────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  SECRETS / GIT SAFETY"
echo "=============================="

cd "$ROOT"
TRACKED_SECRETS=$(git ls-files .env web/.env.local 2>/dev/null || true)
if [[ -z "$TRACKED_SECRETS" ]]; then
  ok "No .env files tracked by git"
else
  fail "Sensitive file(s) tracked by git: $TRACKED_SECRETS"
fi

STAGED_SECRETS=$(git diff --cached --name-only 2>/dev/null | grep -E '(^|/)\.env' || true)
if [[ -z "$STAGED_SECRETS" ]]; then
  ok "No .env files staged for commit"
else
  fail "Sensitive file(s) staged: $STAGED_SECRETS"
fi

# ─── 2. Required env vars ────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  ENV VARS"
echo "=============================="

if [[ -f "$WEB/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$WEB/.env.local"
  set +a
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  ok "DATABASE_URL is set"
else
  fail "DATABASE_URL is not set (check web/.env.local or environment)"
fi

# ─── 3. Python syntax ────────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  PYTHON SYNTAX"
echo "=============================="

PYTHON="${ROOT}/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3

PY_ERRORS=0
while IFS= read -r -d '' f; do
  if ! "$PYTHON" -m py_compile "$f" 2>/tmp/py_err; then
    echo "  syntax error in $f: $(cat /tmp/py_err)"
    PY_ERRORS=$((PY_ERRORS + 1))
  fi
done < <(find "$ROOT" -name "*.py" -not -path "*/.venv/*" -not -path "*/__pycache__/*" -print0)

if [[ $PY_ERRORS -eq 0 ]]; then
  ok "All Python files parse cleanly"
else
  fail "$PY_ERRORS Python file(s) have syntax errors"
fi

# ─── 4. DB connectivity + data freshness ─────────────────────────────────────
echo ""
echo "=============================="
echo "  DATABASE CONNECTIVITY"
echo "=============================="

if [[ -n "${DATABASE_URL:-}" ]]; then
  DB_RESULT=$("$PYTHON" - <<'PYEOF' 2>/tmp/db_err
import os, sys
from datetime import datetime, timezone, timedelta

try:
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM accelerator_companies")
    companies = cur.fetchone()[0]
    print(f"  accelerator_companies: {companies}")

    cur.execute("SELECT COUNT(*) FROM edgar_filings")
    filings = cur.fetchone()[0]
    print(f"  edgar_filings: {filings}")

    cur.execute("SELECT MAX(date_filed) FROM edgar_filings")
    latest = cur.fetchone()[0]
    if latest:
        age = (datetime.now(timezone.utc).date() - latest).days
        print(f"  newest filing: {latest} ({age} days ago)")
        if age > 14:
            print(f"STALE:{age}")
    conn.close()
    sys.exit(0)
except Exception as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
PYEOF
  ) && DB_OK=true || DB_OK=false

  if $DB_OK; then
    echo "$DB_RESULT" | grep -v '^STALE:'
    ok "Database is reachable"
    STALE_AGE=$(echo "$DB_RESULT" | grep '^STALE:' | cut -d: -f2 || true)
    if [[ -n "$STALE_AGE" ]]; then
      warn "Newest EDGAR filing is ${STALE_AGE} days old — pipeline may need a run before deploying"
    fi
  else
    cat /tmp/db_err >&2
    fail "Cannot connect to database"
  fi
else
  fail "Skipped — DATABASE_URL not set"
fi

# ─── 5. Python lint (ruff) ────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  PYTHON LINT (ruff)"
echo "=============================="

cd "$ROOT"
if uv run ruff check . 2>&1; then
  ok "ruff passed"
else
  fail "ruff reported errors"
fi

# ─── 6. Next.js build (TypeScript + compilation) ──────────────────────────────
echo ""
echo "=============================="
echo "  NEXT.JS BUILD"
echo "=============================="

cd "$WEB"
if npm run build --silent 2>&1 | tail -5; then
  ok "next build succeeded"
else
  fail "next build failed"
fi

# ─── 7. ESLint ───────────────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  ESLINT"
echo "=============================="

if npm run lint --silent 2>&1; then
  ok "ESLint passed"
else
  fail "ESLint reported errors"
fi

# ─── 8. Summary ──────────────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  SUMMARY"
echo "=============================="
echo "  Passed: $PASS  |  Warned: $WARN  |  Failed: $FAIL"

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "  Fix the failures above before deploying."
  exit 1
elif [[ $WARN -gt 0 ]]; then
  echo ""
  echo "  Warnings present — review before deploying."
else
  echo ""
  echo "  All checks passed. Safe to deploy."
fi
