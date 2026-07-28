#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/payshield_pg_${TIMESTAMP}.dump"
S3_BUCKET="${S3_BUCKET:-s3://payshield-backups/postgres/}"

mkdir -p "${BACKUP_DIR}"

PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-payshield}"
PGDB="${PGDB:-payshield}"

echo "[$(date)] Starting PostgreSQL backup: ${PGDB}@${PGHOST}:${PGPORT}"

pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDB}" \
  --format=custom \
  --compress=9 \
  --verbose \
  --file="${BACKUP_FILE}" 2>&1

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup completed: ${BACKUP_FILE} (${BACKUP_SIZE})"

if [ -n "${S3_BUCKET}" ]; then
    echo "[$(date)] Uploading to S3..."
    aws s3 cp "${BACKUP_FILE}" "${S3_BUCKET}"
    echo "[$(date)] Upload complete"
fi

echo "[$(date)] Cleaning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "payshield_pg_*.dump" -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date)] Backup process finished successfully"
