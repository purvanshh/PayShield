#!/usr/bin/env python3
"""Seed Redis with initial configuration and default rules."""

import json
import logging

from infrastructure.redis_bridge import create_sync_redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _seed_return_risk(redis):
    """Seed return-risk demo profiles (Track 02) so the scorer has real inputs."""
    profiles = {
        "U001": {
            "return_rate_30d": 0.05,
            "return_rate_90d": 0.06,
            "return_rate_lifetime": 0.05,
            "total_orders": 41,
            "total_returns": 2,
            "avg_return_value": 1200.00,
            "max_return_value": 2500.00,
            "return_reason_distribution": json.dumps({"DEFECTIVE": 1, "CHANGED_MIND": 1}),
            "cod_refusal_rate": 0.0,
            "cod_refusals": 0,
            "serial_returner_flag": "false",
            "return_velocity_7d": 0,
            "first_return_days": 60,
            "return_pattern_score": 0.8,
            "last_return_ts": "2026-07-02T10:00:00",
        },
        "U002": {
            "return_rate_30d": 0.12,
            "return_rate_90d": 0.10,
            "return_rate_lifetime": 0.11,
            "total_orders": 27,
            "total_returns": 3,
            "avg_return_value": 2600.00,
            "max_return_value": 5400.00,
            "return_reason_distribution": json.dumps({"SIZE_ISSUE": 2, "QUALITY_ISSUE": 1}),
            "cod_refusal_rate": 0.08,
            "cod_refusals": 1,
            "serial_returner_flag": "false",
            "return_velocity_7d": 1,
            "first_return_days": 21,
            "return_pattern_score": 0.6,
            "last_return_ts": "2026-08-14T10:00:00",
        },
        "U003": {
            "return_rate_30d": 0.62,
            "return_rate_90d": 0.55,
            "return_rate_lifetime": 0.56,
            "total_orders": 18,
            "total_returns": 10,
            "avg_return_value": 3800.00,
            "max_return_value": 8600.00,
            "return_reason_distribution": json.dumps({"SIZE_ISSUE": 5, "CHANGED_MIND": 4, "DEFECTIVE": 1}),
            "cod_refusal_rate": 0.42,
            "cod_refusals": 5,
            "serial_returner_flag": "true",
            "return_velocity_7d": 3,
            "first_return_days": 6,
            "return_pattern_score": 0.35,
            "last_return_ts": "2026-08-19T10:00:00",
        },
        "U004": {
            "return_rate_30d": 0.24,
            "return_rate_90d": 0.21,
            "return_rate_lifetime": 0.22,
            "total_orders": 33,
            "total_returns": 7,
            "avg_return_value": 5100.00,
            "max_return_value": 9800.00,
            "return_reason_distribution": json.dumps({"NOT_AS_DESCRIBED": 3, "DEFECTIVE": 3, "OTHER": 1}),
            "cod_refusal_rate": 0.0,
            "cod_refusals": 0,
            "serial_returner_flag": "false",
            "return_velocity_7d": 2,
            "first_return_days": 14,
            "return_pattern_score": 0.5,
            "last_return_ts": "2026-08-10T10:00:00",
        },
    }
    for uid, fields in profiles.items():
        for key, value in fields.items():
            redis.hset(f"return_risk:user:{uid}", key, value)
        logger.info("Seeded return-risk profile %s", uid)

    redis.hset("return_risk:merchant:M001", "return_rate_30d", 0.28)
    redis.hset("return_risk:merchant:M001", "avg_resolution_hours", 26.5)
    redis.hset("return_risk:merchant:M001", "return_fraud_rate", 0.03)
    redis.zadd("return_risk:merchant:M001:category", {"fashion": 0.35, "electronics": 0.12})
    logger.info("Seeded return-risk merchant M001")

    redis.set(
        "config:return_risk:tiers",
        json.dumps({
            "LOW": {"max_score": 0.30, "action": "ACCEPT"},
            "MEDIUM": {"max_score": 0.70, "action": "FLAG_FOR_REVIEW"},
            "HIGH": {"max_score": 1.00, "action": "REQUIRE_PREPAID"},
        }),
    )


def _seed_chargeback(redis):
    """Seed chargeback responder configuration (Track 02)."""
    redis.set("config:chargeback:confidence_threshold", json.dumps({"value": 0.6, "comment": "Min completeness to auto-REJECT"}))
    redis.set("config:chargeback:auto_submit", json.dumps({"value": False, "comment": "Human-in-the-loop submission"}))
    redis.set(
        "config:chargeback:deadline_days",
        json.dumps({"UPI": 7, "VISA": 30, "MASTERCARD": 30, "AMEX": 20, "RUPAY": 15}),
    )
    logger.info("Seeded chargeback configuration")


def main():
    redis = create_sync_redis()

    if not redis.ping():
        logger.error("Redis is not available. Aborting.")
        return

    logger.info("Seeding Redis with default rules...")
    redis.set("config:threshold:fraud_probability", json.dumps({"value": 0.85, "comment": "Global fraud probability threshold"}))
    redis.set("config:threshold:velocity_zscore", json.dumps({"value": 3.0, "comment": "Z-score threshold for velocity checks"}))
    redis.set("config:threshold:geo_velocity_max_kmh", json.dumps({"value": 900.0, "comment": "Max allowed geo velocity km/h"}))
    redis.set("config:threshold:benford_chi2", json.dumps({"value": 15.51, "comment": "Benford chi2 critical value (p=0.05)"}))

    redis.set("ensemble:weights", json.dumps({
        "layer1_weight": 0.3,
        "layer2_weight": 0.7,
        "fraud_threshold": 0.85,
        "updated_at": "",
    }))

    _seed_return_risk(redis)
    _seed_chargeback(redis)

    logger.info("Redis seeded successfully.")
    redis.close()


if __name__ == "__main__":
    main()
