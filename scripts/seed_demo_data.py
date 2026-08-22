#!/usr/bin/env python3
"""Seed curated demo data for the Track 2 pitch (Phase 22).

Seeds Redis (return-risk profiles, velocity histories, device index,
Benford distributions) and the tamper-evident audit chain with six curated
scenarios whose outcomes are known and explainable:

1. TXN_CLEAN_001    clean transaction            -> ALLOW
2. TXN_SUSPICIOUS   suspicious burst + geo jump  -> BLOCK (V-RULE/G-RULE)
3. ORD_SERIAL_001   serial returner order        -> HIGH risk
4. ORD_HONEST_001   honest electronics order     -> LOW risk
5. CB_WINNABLE_001  well-evidenced dispute       -> REJECT
6. CB_WEAK_001      new-user dispute             -> conservative ACCEPT/PARTIAL

Expected outputs are documented in docs/DEMO_DATA.md and were verified
against this exact seed.

Usage: python scripts/seed_demo_data.py [--redis-url]
"""

import argparse
import json
import logging
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def seed_demo_data(redis=None, seed_velocity_lists: bool = True, audit_writer=None):
    """Run the full seed. ``redis`` defaults to the live sync client.

    The function accepts any object with hset/zadd/hmset/... so it can be
    exercised against doubles for verification; ``audit_writer`` defaults to
    the standard JSONL ``AuditLogWriter`` (store/audit_logs).
    """
    if redis is None:
        from infrastructure.redis_bridge import create_sync_redis

        redis = create_sync_redis()
    if audit_writer is None:
        from store.audit_log import AuditLogWriter

        audit_writer = AuditLogWriter()

    steps = [
        ("clean transaction user + device", _seed_clean_transaction_user),
        ("suspicious user + shared device", _seed_suspicious_user),
        ("serial returner", _seed_serial_returner),
        ("honest customer", _seed_honest_customer),
        ("merchant baselines", _seed_merchants),
        ("chargeback audit chain", _seed_chargeback_audit_log),
    ]
    for label, fn in steps:
        fn(redis, audit_writer)
        logger.info("seeded %s", label)

    if seed_velocity_lists:
        _seed_velocity_histories(redis)
        logger.info("seeded velocity histories")

    logger.info("demo data ready for recording")
    return redis


# --------------------------------------------------------------------------- #
# profiles                                                                     #
# --------------------------------------------------------------------------- #


def _seed_clean_transaction_user(redis, audit_writer):  # noqa: ARG001 - uniform seed step signature
    redis.hmset(
        "return_risk:user:U_CLEAN_001",
        {
            "total_orders": "20",
            "total_returns": "2",
            "return_rate_30d": "0.05",
            "return_rate_90d": "0.10",
            "avg_return_value": "2000",
            "serial_returner": "false",
            "cod_refusals": "0",
            "cod_orders": "5",
            "last_activity": (datetime.utcnow() - timedelta(days=30)).isoformat(),
        },
    )
    redis.hmset(
        "dfp:DEV_CLEAN_001",
        {
            "user_id": "U_CLEAN_001",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)",
            "features": json.dumps(["ip:10.11.42.7", "tz:Asia/Kolkata", "lang:en"]),
            "first_seen": (datetime.utcnow() - timedelta(days=210)).isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        },
    )


def _seed_suspicious_user(redis, audit_writer):  # noqa: ARG001 - uniform seed step signature
    redis.hmset(
        "return_risk:user:U_FRAUD_001",
        {
            "total_orders": "5",
            "total_returns": "4",
            "return_rate_30d": "0.80",
            "return_rate_90d": "0.80",
            "avg_return_value": "8000",
            "serial_returner": "true",
            "cod_refusals": "3",
            "cod_orders": "8",
        },
    )
    import time as _time

    redis.zadd(
        "return_risk:user:U_FRAUD_001:returns",
        {f"ORD_FRAUD_{i}": _time.time() - timedelta(days=i * 2).total_seconds() for i in range(3)},
    )
    # shared with three known-fraud users
    redis.sadd("ud:DEV_SHARED_001", "U_FRAUD_001", "U_RING_001", "U_RING_002")
    redis.hmset(
        "dfp:DEV_SHARED_001",
        {
            "user_id": "U_RING_001",
            "user_agent": "Mozilla/5.0 (Linux; Android 13)",
            "features": json.dumps(["ip:45.12.10.9", "tz:Asia/Kolkata"]),
            "first_seen": (datetime.utcnow() - timedelta(days=4)).isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        },
    )


def _seed_serial_returner(redis, audit_writer):  # noqa: ARG001 - uniform seed step signature
    redis.hmset(
        "return_risk:user:U_SERIAL_001",
        {
            "total_orders": "15",
            "total_returns": "10",
            "return_rate_30d": "0.66",
            "return_rate_90d": "0.66",
            "avg_return_value": "4500",
            "serial_returner": "true",
            "cod_refusals": "3",
            "cod_orders": "8",
            "return_reason_distribution": json.dumps(
                {"CHANGED_MIND": 5, "SIZE_ISSUE": 3, "DEFECTIVE": 2}
            ),
        },
    )
    now = time.time()
    redis.zadd(
        "return_risk:user:U_SERIAL_001:returns",
        {f"ORD_SERIAL_{i}": now - timedelta(days=i * 2).total_seconds() for i in range(3)},
    )


def _seed_honest_customer(redis, audit_writer):  # noqa: ARG001 - uniform seed step signature
    redis.hmset(
        "return_risk:user:U_HONEST_001",
        {
            "total_orders": "25",
            "total_returns": "2",
            "return_rate_30d": "0.04",
            "return_rate_90d": "0.08",
            "avg_return_value": "1500",
            "serial_returner": "false",
            "cod_refusals": "0",
            "cod_orders": "3",
        },
    )


def _seed_merchants(redis, audit_writer):  # noqa: ARG001 - uniform seed step signature
    redis.hmset("return_risk:merchant:M_FASHION_001", {"return_rate_30d": "0.30", "avg_resolution_hours": "24"})
    redis.zadd("return_risk:merchant:M_FASHION_001:category", {"fashion": 0.30})
    redis.hmset("return_risk:merchant:M_ELECTRONICS_001", {"return_rate_30d": "0.12", "avg_resolution_hours": "48"})
    redis.zadd(
        "return_risk:merchant:M_ELECTRONICS_001:category",
        {"electronics": 0.12, "fashion": 0.32, "groceries": 0.04, "home": 0.18, "beauty": 0.15},
    )
    # Benford distribution for the fashion merchant (amount bookkeeping normal)
    for digit in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
        redis.hset("benford:M_FASHION_001", digit, str({1: 30, 2: 18, 3: 13, 4: 10, 5: 8, 6: 7, 7: 6, 8: 5, 9: 4}[int(digit)]))
    redis.hset("benford:M_FASHION_001", "total", "101")


def _seed_velocity_histories(redis, *_):
    """Velocity lists used by /v1/score so rule firings are deterministic."""

    def entry(ts, amount, merchant, user, device):
        return json.dumps(
            {"ts": ts, "amount": amount, "merchant": merchant, "user": user, "device": device}
        )

    now = time.time()
    # clean user: 3 txns in the last hour, well within thresholds
    for i, amount in enumerate([2100.0, 2500.0, 2490.0]):
        redis.lpush(
            "velocity:user:U_CLEAN_001",
            entry(now - 1800 - i * 900, amount, "M_FASHION_001", "U_CLEAN_001", "DEV_CLEAN_001"),
        )
    # suspicious user: 12 identical 95k txns inside 5 minutes
    for i in range(12):
        redis.lpush(
            "velocity:user:U_FRAUD_001",
            entry(now - 60 - i * 20, 95000.0, "M_FASHION_001", "U_FRAUD_001", "DEV_SHARED_001"),
        )


# --------------------------------------------------------------------------- #
# audit chain (chargeback scenarios)                                           #
# --------------------------------------------------------------------------- #


def _seed_chargeback_audit_log(redis, audit_writer):  # noqa: ARG001 - uniform seed step signature
    import store.audit_log

    if audit_writer is None:
        audit_writer = store.audit_log.AuditLogWriter()

    # Winnable: clean transaction the pipeline allowed - no rules fired
    audit_writer.append(
        "SCORE_DECISION",
        "U_CLEAN_001",
        "ALLOW",
        {
            "txn_id": "TXN_CLEAN_001",
            "merchant_id": "M_FASHION_001",
            "amount": 2500.00,
            "device_fingerprint": "DEV_CLEAN_001",
            "fraud_probability": 0.08,
            "layer_triggered": "ENSEMBLE",
            "triggered_rules": [],
        },
    )

    # Weak case: brand-new user, no device history, no graph
    audit_writer.append(
        "SCORE_DECISION",
        "U_NEW_001",
        "ALLOW",
        {
            "txn_id": "TXN_NEW_001",
            "merchant_id": "M_FASHION_001",
            "amount": 5000.00,
            "fraud_probability": 0.11,
            "layer_triggered": "ENSEMBLE",
            "triggered_rules": [],
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-velocity", action="store_true", default=True,
                        help="also seed velocity histories the /v1/score demo needs")
    args = parser.parse_args()

    redis = seed_demo_data(seed_velocity_lists=args.seed_velocity)
    if hasattr(redis, "ping") and not redis.ping():
        logger.error("Redis appears unreachable - the return-risk profiles were not persisted")
    elif hasattr(redis, "ping"):
        logger.info("Redis reachable and seeded")


if __name__ == "__main__":
    main()
