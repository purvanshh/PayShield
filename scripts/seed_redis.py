#!/usr/bin/env python3
"""Seed Redis with initial configuration and default rules."""

import json
import logging

from infrastructure.redis_bridge import create_sync_redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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

    logger.info("Redis seeded successfully.")
    redis.close()


if __name__ == "__main__":
    main()
