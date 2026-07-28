#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

usage() {
    echo "Usage: $0 <backup-file> [s3-uri]"
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

echo "[$(date)] Restoring Redis from: ${BACKUP_PATH}"
BACKUP_SIZE=$(du -h "${BACKUP_PATH}" | cut -f1)
echo "[$(date)] Backup size: ${BACKUP_SIZE}"

echo "[$(date)] Stopping Redis and replacing RDB..."
kubectl exec -n payshield deployment/redis -- redis-cli DEBUG CHANGE-REPLICATION-ID
kubectl exec -n payshield deployment/redis -- redis-cli DEBUG SLEEP 2
kubectl cp "${BACKUP_PATH}" payshield/redis:/data/dump.rdb
kubectl exec -n payshield deployment/redis -- chown redis:redis /data/dump.rdb

echo "[$(date)] Restarting Redis..."
kubectl rollout restart -n payshield deployment/redis
kubectl rollout status -n payshield deployment/redis --timeout=120s

echo "[$(date)] Verifying restore..."
sleep 5
RESTORED_KEYS=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" DBSIZE)
echo "[$(date)] Restore complete. Redis contains ${RESTORED_KEYS} keys."

rm -rf "${RESTORE_DIR}"
