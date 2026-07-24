import csv
import hashlib
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import yaml

logger = logging.getLogger(__name__)


class FeatureType(Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"
    STRING = "string"
    VECTOR = "vector"


class FeatureSource(Enum):
    VELOCITY = "velocity"
    DEVICE = "device"
    BASELINE = "baseline"
    GRAPH = "graph"
    TRANSACTION = "transaction"
    DERIVED = "derived"


@dataclass
class FeatureDefinition:
    name: str
    feature_type: FeatureType
    source: FeatureSource
    version: int = 1
    description: str = ""
    nullable: bool = True
    min_val: float | None = None
    max_val: float | None = None
    categories: list[str] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "feature_type": self.feature_type.value,
            "source": self.source.value,
            "version": self.version,
            "description": self.description,
            "nullable": self.nullable,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "categories": self.categories,
        }


@dataclass
class FeatureLogEntry:
    feature_name: str
    value: float | str | bool | None
    version: int
    timestamp: float
    transaction_id: str | None = None
    user_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "feature_name": self.feature_name,
            "value": self.value,
            "version": self.version,
            "timestamp": self.timestamp,
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
        }


class FeatureRegistry:
    REGISTRY_KEY = "feature_registry:definitions"
    LOG_PREFIX = "feature_log"
    DUMP_PREFIX = "feature_dump"

    def __init__(self, redis_client, config_path: str | None = None):
        self.redis = redis_client
        self._definitions: dict[str, FeatureDefinition] = {}
        if config_path:
            self._load_from_config(config_path)

    def _load_from_config(self, config_path: str):
        if not os.path.exists(config_path):
            logger.warning(f"Feature registry config not found: {config_path}")
            return
        with open(config_path) as f:
            data = yaml.safe_load(f)
        for entry in data.get("features", []):
            definition = FeatureDefinition(
                name=entry["name"],
                feature_type=FeatureType(entry["type"]),
                source=FeatureSource(entry["source"]),
                version=entry.get("version", 1),
                description=entry.get("description", ""),
                nullable=entry.get("nullable", True),
                min_val=entry.get("min_val"),
                max_val=entry.get("max_val"),
                categories=entry.get("categories"),
            )
            self._definitions[definition.name] = definition

    def register_definition(self, definition: FeatureDefinition):
        self._definitions[definition.name] = definition

    def get_definition(self, name: str) -> FeatureDefinition | None:
        return self._definitions.get(name)

    def list_features(self, source: FeatureSource | None = None) -> list[FeatureDefinition]:
        if source:
            return [d for d in self._definitions.values() if d.source == source]
        return list(self._definitions.values())

    def get_feature_vector_schema(self) -> list[dict]:
        return [d.to_dict() for d in self._definitions.values()]

    async def log_feature(self, entry: FeatureLogEntry):
        log_key = f"{self.LOG_PREFIX}:{entry.feature_name}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        await self.redis.zadd(log_key, {json.dumps(entry.to_dict()): entry.timestamp})
        await self.redis.expire(log_key, 86400 * 7)

    async def get_feature_logs(self, feature_name: str, date_str: str) -> list[FeatureLogEntry]:
        log_key = f"{self.LOG_PREFIX}:{feature_name}:{date_str}"
        raw = await self.redis.zrangebyscore(log_key, 0, time.time())
        entries = []
        for item in raw:
            data = json.loads(item)
            entries.append(FeatureLogEntry(**data))
        return entries

    async def compute_psi(self, feature_name: str, expected_distribution: dict[str, float]) -> float:
        logs = await self.get_feature_logs(feature_name, datetime.now(timezone.utc).strftime("%Y%m%d"))
        observed_counts: dict[str, float] = {}
        total = 0
        for entry in logs:
            key = str(entry.value)
            observed_counts[key] = observed_counts.get(key, 0) + 1
            total += 1

        if total == 0:
            return 0.0

        psi = 0.0
        for key, expected_pct in expected_distribution.items():
            observed_pct = observed_counts.get(key, 0) / total
            if observed_pct > 0 and expected_pct > 0:
                psi += (observed_pct - expected_pct) * (observed_pct / expected_pct)

        for key, observed_count in observed_counts.items():
            if key not in expected_distribution:
                observed_pct = observed_count / total
                psi += observed_pct * (observed_pct / 0.0001)

        return round(psi, 6)

    def validate_value(self, name: str, value: float | str | bool | None) -> bool:
        definition = self._definitions.get(name)
        if not definition:
            return True
        if value is None:
            return definition.nullable
        if definition.feature_type == FeatureType.NUMERIC:
            if not isinstance(value, (int, float)):
                return False
            if definition.min_val is not None and value < definition.min_val:
                return False
            if definition.max_val is not None and value > definition.max_val:
                return False
        elif definition.feature_type == FeatureType.CATEGORICAL:
            if definition.categories and str(value) not in definition.categories:
                return False
        return True


class FeatureVersionManager:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_version(self, feature_name: str, timestamp: float | None = None) -> int:
        version_key = f"feature_version:{feature_name}"
        raw = await self.redis.get(version_key)
        return int(raw) if raw else 1

    async def bump_version(self, feature_name: str):
        version_key = f"feature_version:{feature_name}"
        await self.redis.set(version_key, str(int(time.time())))
