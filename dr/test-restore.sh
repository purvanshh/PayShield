#!/usr/bin/env bash
set -euo pipefail

echo "=== DR Restore Validation Test ==="
echo "Started: $(date)"
echo ""

PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-payshield}"
PGDB="${PGDB:-payshield}"

failures=0

check() {
    local description="$1"
    shift
    if "$@" 2>/dev/null; then
        echo "[PASS] ${description}"
    else
        echo "[FAIL] ${description}"
        failures=$((failures + 1))
    fi
}

echo "--- Connectivity Checks ---"
check "PostgreSQL is reachable" pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}"
check "Redis is reachable" redis-cli -h "${REDIS_HOST:-redis}" -p "${REDIS_PORT:-6379}" PING

echo ""
echo "--- Data Integrity Checks ---"
check "Transactions table has data" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDB}" -c "SELECT COUNT(*) > 0 FROM transactions" -t | grep -q "t"
check "Rules table has data" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDB}" -c "SELECT COUNT(*) > 0 FROM rules" -t | grep -q "t"
check "Models table has data" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDB}" -c "SELECT COUNT(*) > 0 FROM models" -t | grep -q "t"

echo ""
echo "--- Schema Checks ---"
check "Alembic version exists" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDB}" -c "SELECT COUNT(*) > 0 FROM alembic_version" -t | grep -q "t"

echo ""
echo "--- Application Checks ---"
check "API health endpoint" curl -sf http://localhost:8000/health > /dev/null
check "API ready endpoint" curl -sf http://localhost:8000/ready > /dev/null

echo ""
if [ "${failures}" -eq 0 ]; then
    echo "=== ALL CHECKS PASSED ==="
else
    echo "=== ${failures} CHECK(S) FAILED ==="
fi
exit ${failures}
