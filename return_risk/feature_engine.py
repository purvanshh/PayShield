"""Return-risk feature registry client (Track 02 - Phases 8/13).

Phase 8: loads ``configs/feature_registry_return.yaml`` and exposes:
- the composite weight map (``composite_weights``) used by Phase 15 scoring,
- per-feature records with Redis keys and normalisation ranges.

The extraction logic (reading Redis hashes/zsets per feature and computing
transaction-level features) is implemented in Phase 13.
"""

from pathlib import Path
from typing import Any

import yaml

DEFAULT_REGISTRY_PATH = Path("configs/feature_registry_return.yaml")


class FeatureRegistry:
    def __init__(self, path: Path | str = DEFAULT_REGISTRY_PATH):
        self.path = Path(path)
        self.composite_weights: dict[str, float] = {}
        self.features: list[dict[str, Any]] = []
        self.version: str = "1.0.0"
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.version = str(data.get("version", "1.0.0"))
        self.composite_weights = data.get("composite_weights", {})
        self.features = data.get("features", [])

    def by_kind(self, kind: str) -> list[dict[str, Any]]:
        return [f for f in self.features if f.get("kind") == kind]

    def weight(self, feature_name: str) -> float:
        return float(self.composite_weights.get(feature_name, 0.0))
