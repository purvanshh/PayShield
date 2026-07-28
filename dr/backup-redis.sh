#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/redis}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/payshield_redis_${TIMESTAMP}.rdb"
S3_BUCKET="${S3_BUCKET:-s3://payshield-backups/redis/}"

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting Redis backup from ${REDIS_HOST}:${REDIS_PORT}"

redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" --rdb "${BACKUP_FILE}" 2>&1

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Redis backup completed: ${BACKUP_FILE} (${BACKUP_SIZE})"

if [ -n "${S3_BUCKET}" ]; then
    echo "[$(date)] Uploading to S3..."
    aws s3 cp "${BACKUP_FILE}" "${S3_BUCKET}"
    echo "[$(date)] Upload complete"
fi

echo "[$(date)] Cleaning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "payshield_redis_*.rdb" -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date)] Backup process finished successfully"
