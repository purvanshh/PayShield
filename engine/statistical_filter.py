from dataclasses import dataclass
from typing import Literal


@dataclass
class StatisticalResult:
    decision: Literal["ALLOW", "BLOCK", "ESCALATE"]
    triggered_rules: list[str]
    velocity_stats: dict | None = None
    benford_chi2: float | None = None


class StatisticalFilter:
    def evaluate(self, txn, feature_store) -> StatisticalResult:
        pass
