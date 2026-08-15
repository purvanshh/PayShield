#!/usr/bin/env bash
# demo_replay.sh — curated demo driver for the PayShield recording runbook.
#
# Subcommands:
#   stack           docker compose ps for the 5 services
#   health          API health + seed the "yesterday" PSI baseline
#   prewarm SUFFIX  inject the burst off-camera and wait for the LLM
#                   investigation to finish (dashboard shows it ready)
#   normal SUFFIX   one normal ~4k INR Mumbai txn -> ALLOW
#   burst  SUFFIX   velocity burst: 14 x 95k INR -> ALLOW then REVIEW
#   geo             Mumbai then Delhi 10 min later -> BLOCK (G-RULE-01)
#   investigation TXN_ID   poll + print the LLM report
#   drift           PSI drift report (yesterday vs today)
#
# Environment: PAYSHIELD_BASE (default http://localhost:8000), ADMIN_USER/ADMIN_PASS
set -euo pipefail

BASE="${PAYSHIELD_BASE:-http://localhost:8000/v1}"
ADMIN_USER="${ADMIN_USERNAME:-admin}"
ADMIN_PASS="${ADMIN_PASSWORD:-admin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE="docker compose -f $ROOT/docker/docker-compose.yml"
TOKEN_FILE="/tmp/payshield_demo_token"

pretty() { python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))'; }

login() {
    local raw
    raw=$(curl -sS -X POST "$BASE/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
    TOKEN=$(printf '%s' "$raw" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
    printf '%s' "$TOKEN" > "$TOKEN_FILE"
}

_auth() { printf 'Authorization: Bearer %s' "$(cat "$TOKEN_FILE")"; }

score() { # score <txn_id> <user_id> <merchant_id> <amount> <ts> <lat> <lon>
    curl -sS -X POST "$BASE/score" \
        -H "$(_auth)" -H 'Content-Type: application/json' \
        -d "{\"txn_id\":\"$1\",\"user_id\":\"$2\",\"merchant_id\":\"$3\",\"amount\":$4,
             \"timestamp\":\"$5\",\"device_fingerprint\":\"D_$2\",
             \"location\":{\"lat\":$6,\"lon\":$7},\"txn_type\":\"P2M\"}"
}

# timestamp N seconds away from now (negative -> in the future)
ago_ts() {
    local secs="$1"
    if date -v-1S >/dev/null 2>&1; then
        if [ "$secs" -lt 0 ]; then
            date -u -v+"${secs#-}"S +%Y-%m-%dT%H:%M:%SZ
        else
            date -u -v-"${secs}"S +%Y-%m-%dT%H:%M:%SZ
        fi
    else
        date -u -d "${secs} seconds" +%Y-%m-%dT%H:%M:%SZ
    fi
}

cmd_stack() { $COMPOSE ps; }

_score_endpoint() { curl -sS "$1"; }

cmd_health() {
    echo "== health =="
    _score_endpoint "http://localhost:8000/health" | pretty
    echo "== ready =="
    _score_endpoint "http://localhost:8000/health/ready" | pretty
    echo "== seeding PSI baseline (yesterday window) =="
    $COMPOSE exec -T api python scripts/seed_drift_baseline.py
}

cmd_normal() {
    local suffix="${1:?usage: demo_replay.sh normal SUFFIX}"
    local ts
    ts=$(ago_ts 2)
    score "TXN_NORMAL_${suffix}" "U_NORMAL_${suffix}" "M_FOOD_${suffix}" 4000 "$ts" 19.0760 72.8777 | pretty
}

cmd_burst() {
    local suffix="${1:?usage: demo_replay.sh burst SUFFIX}"
    local i ts res
    for i in $(seq 1 14); do
        ts=$(ago_ts $((14 - i)))
        res=$(score "TXN_BURST_${suffix}_$(printf '%02d' "$i")" "U_BURST_${suffix}" \
            "M_BURST_${suffix}" 9500 "$ts" 19.0760 72.8777)
        echo "== txn $(printf '%02d' "$i") =="
        printf '%s' "$res" | python3 -c '
import json,sys
d=json.load(sys.stdin)
rules=d.get("evidence",{}).get("triggered_rules",[])
row={"txn_id":d["txn_id"],"decision":d["decision"],"fraud_probability":round(d["fraud_probability"],4),
     "latency_ms":d["latency_ms"],"triggered_rules":rules,
     "breakdown":d.get("evidence",{}).get("latency_breakdown",{})}
print(json.dumps(row, indent=2))'
    done
}

cmd_geo() {
    local suffix="${1:-$(date +%H%M%S)}" ts ts2
    ts=$(ago_ts 2)
    score "TXN_GEO_${suffix}_01" "U_GEO_${suffix}" "M_GEO_A_${suffix}" 3000 "$ts" 19.0760 72.8777 | pretty
    ts2=$(ago_ts -600)
    score "TXN_GEO_${suffix}_02" "U_GEO_${suffix}" "M_GEO_B_${suffix}" 3000 "$ts2" 28.6139 77.2090 | pretty
}

cmd_prewarm() {
    local suffix="${1:?usage: demo_replay.sh prewarm SUFFIX}"
    # Drop any leftover investigation tasks from earlier takes so the LLM
    # queue only contains this take's investigations (CPU generation is slow).
    $COMPOSE exec -T worker celery -A tasks.celery_app purge -f >/dev/null 2>&1 || true
    cmd_burst "$suffix"
    cmd_investigation "TXN_BURST_${suffix}_14"
}

cmd_investigation() {
    local txn_id="${1:?usage: demo_replay.sh investigation TXN_ID}"
    local tries=120 code
    echo "== polling investigation $txn_id (LLM generation on CPU takes minutes) =="
    for i in $(seq 1 "$tries"); do
        code=$(curl -sS -o /tmp/payshield_inv.json -w '%{http_code}' \
            -H "$(_auth)" "$BASE/investigation/$txn_id" || echo 000)
        if [ "$code" = "200" ]; then
            python3 -c '
import json
d=json.load(open("/tmp/payshield_inv.json"))
print(json.dumps({k:d.get(k) for k in ("txn_id","fraud_type","confidence","recommended_action","key_evidence","narrative")}, indent=2, default=str))'
            return 0
        fi
        if [ $((i % 12)) -eq 0 ]; then
            echo "  ...still generating ($((i * 5))s elapsed, HTTP $code)"
        fi
        sleep 5
    done
    echo "timed out waiting for investigation $txn_id" >&2
    return 1
}

cmd_drift() {
    local host="${PAYSHIELD_BASE:-http://localhost:8000}"
    echo "== PSI drift report (yesterday vs today) =="
    curl -sS -H "$(_auth)" "$host/admin/drift/psi" | pretty
}

cmd_help() {
    echo "usage: bash scripts/demo_replay.sh <stack|health|normal|burst|geo|prewarm|investigation|drift> [SUFFIX|TXN_ID]"
}

login
case "${1:-}" in
    stack) cmd_stack ;;
    health) cmd_health ;;
    normal) cmd_normal "${2:-DEMO}" ;;
    burst) cmd_burst "${2:-DEMO}" ;;
    geo) cmd_geo ;;
    prewarm) cmd_prewarm "${2:-DEMO}" ;;
    investigation) cmd_investigation "${2:?txn id required}" ;;
    drift) cmd_drift ;;
    *) cmd_help ;;
esac