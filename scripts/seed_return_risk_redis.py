#!/usr/bin/env python3
"""Seed Redis with synthetic return-risk profiles (Phase 17).

Regenerates the deterministic synthetic dataset (seed 42) and writes
user/merchant profiles into the ``return_risk:*`` keys the feature engine
consumes, so the scorer (and the demo) runs end-to-end without manual
data entry.

Usage: python scripts/seed_return_risk_redis.py [--users-per-type 20] [--orders-per-user 20]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument("--users-per-type", type=int, default=20)
    parser.add_argument("--orders-per-user", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from data.synthetic.return_generator import ReturnRiskSyntheticGenerator

    dataset = ReturnRiskSyntheticGenerator(seed=args.seed).generate_dataset(
        num_users_per_type=args.users_per_type, orders_per_user=args.orders_per_user
    )

    from infrastructure.redis_bridge import create_sync_redis

    redis = create_sync_redis()
    if not redis.ping():
        logger.error("Redis is not available. Aborting.")
        return

    seeded = ReturnRiskSyntheticGenerator(seed=args.seed).seed_redis_with_profiles(redis, dataset)
    logger.info(
        "Seeded %d user profiles (%d orders) + merchant baselines",
        seeded,
        len(dataset["orders"]),
    )
    redis.close()


if __name__ == "__main__":
    main()
