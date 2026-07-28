#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/config}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/payshield_config_${TIMESTAMP}.tar.gz"
S3_BUCKET="${S3_BUCKET:-s3://payshield-backups/config/}"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting configuration backup"

CONFIG_DIRS=(
    "configs/"
    "k8s/"
    "docker/"
    ".env"
    "pyproject.toml"
    "requirements.txt"
    "requirements-dev.txt"
    "Makefile"
    "alembic.ini"
)

DIRS_TO_BACKUP=()
for dir in "${CONFIG_DIRS[@]}"; do
    if [ -e "${dir}" ]; then
        DIRS_TO_BACKUP+=("${dir}")
    fi
done

tar -czf "${BACKUP_FILE}" "${DIRS_TO_BACKUP[@]}" 2>&1

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Config backup completed: ${BACKUP_FILE} (${BACKUP_SIZE})"

if [ -n "${S3_BUCKET}" ]; then
    echo "[$(date)] Uploading to S3..."
    aws s3 cp "${BACKUP_FILE}" "${S3_BUCKET}"
    echo "[$(date)] Upload complete"
fi

echo "[$(date)] Config backup finished successfully"
