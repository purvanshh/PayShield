#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo "  PayShield Backup Status Monitor"
echo "  $(date)"
echo "============================================"
echo ""

S3_BUCKET="${S3_BUCKET:-s3://payshield-backups}"

check_backup() {
    local name="$1"
    local path="$2"
    local max_age_hours="$3"

    if aws s3 ls "${path}" --recursive 2>/dev/null | grep -q .; then
        LATEST=$(aws s3 ls "${path}" --recursive | sort | tail -1)
        TIMESTAMP=$(echo "${LATEST}" | awk '{print $1, $2}')
        SIZE=$(echo "${LATEST}" | awk '{print $3}')
        NOW=$(date +%s)
        FILE_TS=$(date -d "${TIMESTAMP}" +%s 2>/dev/null || echo "${NOW}")
        AGE_HOURS=$(( (NOW - FILE_TS) / 3600 ))

        if [ "${AGE_HOURS}" -le "${max_age_hours}" ]; then
            echo "[OK] ${name}: ${AGE_HOURS}h old, $(numfmt --to=iec ${SIZE})"
            return 0
        else
            echo "[WARN] ${name}: ${AGE_HOURS}h old (max ${max_age_hours}h)"
            return 1
        fi
    else
        echo "[CRIT] ${name}: No backups found"
        return 2
    fi
}

EXIT_CODE=0

check_backup "PostgreSQL" "${S3_BUCKET}/postgres/" 12 || EXIT_CODE=$?
check_backup "Redis" "${S3_BUCKET}/redis/" 36 || EXIT_CODE=$?
check_backup "Configuration" "${S3_BUCKET}/config/" 36 || EXIT_CODE=$?

echo ""
if [ "${EXIT_CODE}" -eq 0 ]; then
    echo "All backups healthy"
else
    echo "Some backups need attention"
fi

exit "${EXIT_CODE}"
