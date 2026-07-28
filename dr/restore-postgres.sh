#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <backup-file> [s3-uri]"
    echo "  backup-file   Local path or S3 URI of the backup to restore"
    echo "  s3-uri        Optional S3 URI to download backup from"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

BACKUP_SOURCE="$1"
RESTORE_DIR="/tmp/restore"
mkdir -p "${RESTORE_DIR}"

if [[ "${BACKUP_SOURCE}" == s3://* ]]; then
    echo "[$(date)] Downloading backup from S3: ${BACKUP_SOURCE}"
    aws s3 cp "${BACKUP_SOURCE}" "${RESTORE_DIR}/"
    BACKUP_FILE=$(basename "${BACKUP_SOURCE}")
    BACKUP_PATH="${RESTORE_DIR}/${BACKUP_FILE}"
else
    BACKUP_PATH="${BACKUP_SOURCE}"
fi

if [ ! -f "${BACKUP_PATH}" ]; then
    echo "Error: Backup file not found: ${BACKUP_PATH}"
    exit 1
fi

BACKUP_SIZE=$(du -h "${BACKUP_PATH}" | cut -f1)
echo "[$(date)] Restoring PostgreSQL from: ${BACKUP_PATH} (${BACKUP_SIZE})"

PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-payshield}"
PGDB="${PGDB:-payshield}"

echo "[$(date)] Terminating existing connections..."
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "postgres" <<-EOSQL
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = '${PGDB}' AND pid <> pg_backend_pid();
EOSQL

echo "[$(date)] Dropping and recreating database..."
dropdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" --if-exists "${PGDB}"
createdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "${PGDB}"

echo "[$(date)] Restoring data..."
pg_restore -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDB}" \
    --verbose \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    "${BACKUP_PATH}" 2>&1

echo "[$(date)] Running post-restore analysis..."
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDB}" <<-EOSQL
    ANALYZE;
    SELECT 'Tables restored: ' || COUNT(*)::text FROM information_schema.tables WHERE table_schema = 'public';
EOSQL

echo "[$(date)] Restore completed successfully"

rm -rf "${RESTORE_DIR}"
