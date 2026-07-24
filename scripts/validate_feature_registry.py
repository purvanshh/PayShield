import argparse
import asyncio
import json
import logging
import os

import yaml

from store.feature_registry import FeatureDefinition, FeatureRegistry, FeatureSource, FeatureType
from store.feature_vector import FeatureVectorBuilder
from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Validate feature registry")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--config", default="configs/feature_registry.yaml")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"ERROR: Config not found: {args.config}")
        return

    client = AsyncRedisClient(host=args.host, port=args.port)
    registry = FeatureRegistry(client, config_path=args.config)

    print(f"\nFeature Registry Validation")
    print(f"{'='*60}")

    definitions = registry.list_features()
    print(f"\nRegistered features: {len(definitions)}")

    sources: dict[str, int] = {}
    for d in definitions:
        sources[d.source.value] = sources.get(d.source.value, 0) + 1

    print(f"\nBy source:")
    for source, count in sorted(sources.items()):
        print(f"  {source}: {count}")

    missing_descriptions = [d.name for d in definitions if not d.description]
    if missing_descriptions:
        print(f"\nWARNING: {len(missing_descriptions)} features missing descriptions")

    no_range = [d.name for d in definitions if d.feature_type == FeatureType.NUMERIC and d.min_val is None]
    if no_range:
        print(f"\nNOTE: {len(no_range)} numeric features without min/max bounds")

    schema = registry.get_feature_vector_schema()
    print(f"\nFeature vector schema ({len(schema)} fields):")
    for entry in schema[:5]:
        print(f"  {entry['name']:25s} {entry['feature_type']:12s} v{entry['version']}")
    if len(schema) > 5:
        print(f"  ... and {len(schema) - 5} more")

    print(f"\nValidating values...")
    test_cases = [
        ("txn_count_1m", 5, True),
        ("txn_count_1m", -1, False),
        ("device_jaccard_similarity", 0.5, True),
        ("device_jaccard_similarity", 1.5, False),
        ("is_weekend", 0, True),
        ("is_weekend", 2, False),
    ]
    for name, value, expected in test_cases:
        result = registry.validate_value(name, value)
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] validate({name}, {value}) = {result} (expected {expected})")

    builder = FeatureVectorBuilder(registry)
    print(f"\nFeature vector builder ready: {builder.__class__.__name__}")

    print(f"\nFeature store structure:")
    config_data = yaml.safe_load(open(args.config))
    print(f"  PSI threshold: {config_data['skew_detection']['psi_threshold']}")
    print(f"  Min samples:   {config_data['skew_detection']['min_samples']}")

    await client.close()
    print(f"\n{'='*60}")
    print("Validation complete.")


if __name__ == "__main__":
    asyncio.run(main())
