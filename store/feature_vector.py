import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from store.feature_registry import FeatureLogEntry, FeatureRegistry

logger = logging.getLogger(__name__)


@dataclass
class FeatureVector:
    user_id: str
    transaction_id: str | None = None
    features: dict[str, float | str | bool | None] = field(default_factory=dict)
    meta: dict[str, str | int | float] = field(default_factory=dict)
    training_timestamp: datetime | None = None
    serving_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "transaction_id": self.transaction_id,
            "features": {k: v for k, v in self.features.items() if v is not None},
            "meta": self.meta,
            "training_timestamp": self.training_timestamp.isoformat() if self.training_timestamp else None,
            "serving_timestamp": self.serving_timestamp.isoformat(),
            "version": self.version,
        }

    def to_csv_row(self) -> list[str]:
        row = [
            self.user_id,
            self.transaction_id or "",
            str(self.training_timestamp or ""),
            str(self.serving_timestamp),
            str(self.version),
        ]
        for val in self.features.values():
            row.append(str(val) if val is not None else "")
        return row

    @staticmethod
    def csv_header(feature_names: list[str]) -> list[str]:
        return ["user_id", "transaction_id", "training_timestamp", "serving_timestamp", "version"] + feature_names


class FeatureVectorBuilder:
    def __init__(self, registry: FeatureRegistry):
        self.registry = registry

    async def build(
        self,
        user_id: str,
        transaction_id: str | None = None,
        velocity_features: dict[str, float] | None = None,
        device_features: dict[str, float] | None = None,
        baseline_features: dict[str, float] | None = None,
        graph_features: dict[str, float] | None = None,
        transaction_features: dict[str, float] | None = None,
        point_in_time: datetime | None = None,
    ) -> FeatureVector:
        vector = FeatureVector(
            user_id=user_id,
            transaction_id=transaction_id,
            training_timestamp=point_in_time,
        )

        all_features: dict = {}
        all_features.update(velocity_features or {})
        all_features.update(device_features or {})
        all_features.update(baseline_features or {})
        all_features.update(graph_features or {})
        all_features.update(transaction_features or {})

        for name, value in all_features.items():
            definition = self.registry.get_definition(name)
            if definition and self.registry.validate_value(name, value) or definition is None:
                vector.features[name] = value
            else:
                logger.warning(f"Feature '{name}' failed validation (value={value}), excluding")

        vector.meta["feature_count"] = len(vector.features)
        vector.meta["sources"] = ",".join(self._identify_sources(all_features))

        for name, value in vector.features.items():
            entry = self.registry.get_definition(name)
            version = entry.version if entry else 1
            await self.registry.log_feature(
                FeatureLogEntry(
                    feature_name=name,
                    value=value,
                    version=version,
                    timestamp=time.time(),
                    transaction_id=transaction_id,
                    user_id=user_id,
                )
            )

        return vector

    def _identify_sources(self, features: dict) -> list[str]:
        sources = set()
        for name in features:
            definition = self.registry.get_definition(name)
            if definition:
                sources.add(definition.source.value)
        return list(sources)

    @staticmethod
    def feature_vector_to_arff(vector: FeatureVector) -> str:
        lines = ["@RELATION payshield_features"]
        for name, value in vector.features.items():
            if isinstance(value, bool):
                lines.append(f"@ATTRIBUTE {name} {{True,False}}")
            elif isinstance(value, (int, float)):
                lines.append(f"@ATTRIBUTE {name} NUMERIC")
            else:
                lines.append(f"@ATTRIBUTE {name} STRING")
        lines.append("@DATA")
        values = [str(v) if v is not None else "?" for v in vector.features.values()]
        lines.append(",".join(values))
        return "\n".join(lines)


class PointInTimeFeatureExtractor:
    def __init__(self, registry: FeatureRegistry, redis_client):
        self.registry = registry
        self.redis = redis_client

    async def extract_training_vector(
        self,
        user_id: str,
        at_time: datetime,
        velocity_features_fn=None,
        device_features_fn=None,
        baseline_features_fn=None,
    ) -> FeatureVector:
        builder = FeatureVectorBuilder(self.registry)

        velocity_features = None
        if velocity_features_fn:
            velocity_features = await velocity_features_fn(user_id)

        device_features = None
        if device_features_fn:
            device_features = {"device_context": 1.0}

        baseline_features = None
        if baseline_features_fn:
            baseline_features = await baseline_features_fn(user_id)

        return await builder.build(
            user_id=user_id,
            point_in_time=at_time,
            velocity_features=velocity_features,
            device_features=device_features,
            baseline_features=baseline_features,
        )

    async def extract_serving_vector(
        self,
        user_id: str,
        transaction_id: str,
        velocity_features: dict[str, float] | None = None,
        device_features: dict[str, float] | None = None,
        baseline_features: dict[str, float] | None = None,
        transaction_features: dict[str, float] | None = None,
    ) -> FeatureVector:
        builder = FeatureVectorBuilder(self.registry)
        return await builder.build(
            user_id=user_id,
            transaction_id=transaction_id,
            velocity_features=velocity_features,
            device_features=device_features,
            baseline_features=baseline_features,
            transaction_features=transaction_features,
        )
