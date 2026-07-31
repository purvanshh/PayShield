import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class EvidenceItem:
    type: Literal["RULE", "GRAPH", "SHAP", "VELOCITY", "GEO", "BENFORD"]
    description: str
    severity: Literal[1, 2, 3, 4, 5] = 1
    source: Literal["layer1", "layer2", "explainer"] = "layer1"
    importance: float = 0.0


@dataclass
class SHAPFeatureItem:
    name: str
    value: float
    shap_value: float


@dataclass
class GraphNodeItem:
    type: str
    id: str
    importance: float


@dataclass
class InvestigationContext:
    txn_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ensemble_decision: str = "ALLOW"
    ensemble_confidence: float = 0.0
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    shap_features: list[SHAPFeatureItem] = field(default_factory=list)
    graph_nodes: list[GraphNodeItem] = field(default_factory=list)
    summary_stats: dict[str, Any] = field(default_factory=dict)


class EvidenceCollector:
    def __init__(self, max_evidence_items: int = 10):
        self.max_evidence_items = max_evidence_items

    def collect(self, txn_id: str, ensemble_result: Any | None = None) -> InvestigationContext:
        items: list[EvidenceItem] = []
        l1 = None
        l2 = None

        if ensemble_result:
            l1 = getattr(ensemble_result, "layer1_result", None)
            l2 = getattr(ensemble_result, "layer2_result", None)

            items.extend(self._collect_layer1_evidence(l1))
            items.extend(self._collect_layer2_evidence(l2))
            items.extend(self._collect_explainer_evidence(l2))

        items = self._deduplicate(items)
        items = self._rank_evidence(items)
        items = items[:self.max_evidence_items]

        shap_list = self._extract_shap(l2)
        graph_list = self._extract_graph_nodes(l2)
        stats = self._build_summary_stats(ensemble_result)

        return InvestigationContext(
            txn_id=txn_id,
            ensemble_decision=getattr(ensemble_result, "decision", "ALLOW") if ensemble_result else "ALLOW",
            ensemble_confidence=getattr(ensemble_result, "confidence", 0.0) if ensemble_result else 0.0,
            evidence_items=items,
            shap_features=shap_list,
            graph_nodes=graph_list,
            summary_stats=stats,
        )

    def _collect_layer1_evidence(self, layer1_result) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        if layer1_result is None:
            return items
        rules = getattr(layer1_result, "triggered_rules", [])
        decision = getattr(layer1_result, "decision", "ALLOW")
        for rule in rules:
            severity = self._rule_severity(rule)
            items.append(EvidenceItem(
                type="RULE",
                description=f"Rule triggered: {rule}",
                severity=severity,
                source="layer1",
                importance=severity / 5.0,
            ))
        if decision == "BLOCK":
            items.append(EvidenceItem(
                type="RULE",
                description="Layer 1 hard block — critical rule violation",
                severity=5,
                source="layer1",
                importance=1.0,
            ))
        return items

    def _collect_layer2_evidence(self, layer2_result) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        if layer2_result is None:
            return items
        prob = getattr(layer2_result, "fraud_probability", 0.0)
        source = getattr(layer2_result, "source", "L2_GNN")
        items.append(EvidenceItem(
            type="GRAPH",
            description=f"GNN fraud probability: {prob:.3f}",
            severity=4 if prob >= 0.85 else 3 if prob >= 0.5 else 1,
            source="layer2",
            importance=prob,
        ))
        graph_feats = getattr(layer2_result, "graph_features", None) or {}
        for key, val in graph_feats.items():
            if isinstance(val, (int, float)) and abs(val) > 0.1:
                items.append(EvidenceItem(
                    type="GRAPH",
                    description=f"Graph feature {key}: {val:.4f}",
                    severity=3 if abs(val) > 0.5 else 2,
                    source="layer2",
                    importance=abs(val),
                ))
        return items

    def _collect_explainer_evidence(self, layer2_result) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        if layer2_result is None:
            return items
        graph_feats = getattr(layer2_result, "graph_features", None) or {}
        vel = graph_feats.get("velocity", {})
        if isinstance(vel, dict):
            count = vel.get("txn_count_5min", 0)
            if count > 5:
                items.append(EvidenceItem(
                    type="VELOCITY",
                    description=f"High transaction velocity: {count} in 5 min",
                    severity=4 if count > 20 else 3,
                    source="explainer",
                    importance=min(1.0, count / 50),
                ))
            amount = vel.get("amount_sum_1h", 0)
            if amount > 100000:
                items.append(EvidenceItem(
                    type="VELOCITY",
                    description=f"High amount velocity: ₹{amount:,.0f} in 1h",
                    severity=4,
                    source="explainer",
                    importance=min(1.0, amount / 500000),
                ))
        geo = graph_feats.get("geo", {})
        if isinstance(geo, dict):
            deviation = geo.get("location_deviation_km", 0)
            if deviation > 100:
                items.append(EvidenceItem(
                    type="GEO",
                    description=f"Geo anomaly: {deviation:.0f} km location deviation",
                    severity=4 if deviation > 500 else 3,
                    source="explainer",
                    importance=min(1.0, deviation / 1000),
                ))
        benford = graph_feats.get("benford", {})
        if isinstance(benford, dict):
            chi2 = benford.get("chi2", 0)
            if chi2 > 30:
                items.append(EvidenceItem(
                    type="BENFORD",
                    description=f"Benford deviation: χ²={chi2:.1f}",
                    severity=4 if chi2 > 60 else 3,
                    source="explainer",
                    importance=min(1.0, chi2 / 100),
                ))
        return items

    def _deduplicate(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        seen_descriptions: set[str] = set()
        deduplicated: list[EvidenceItem] = []
        for item in sorted(items, key=lambda x: x.importance, reverse=True):
            key = item.description[:60]
            if key not in seen_descriptions:
                seen_descriptions.add(key)
                deduplicated.append(item)
        return deduplicated

    def _rank_evidence(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        scored = []
        for item in items:
            score = item.severity * (0.5 + 0.5 * item.importance)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def _extract_shap(self, layer2_result) -> list[SHAPFeatureItem]:
        if layer2_result is None:
            return []
        graph_feats = getattr(layer2_result, "graph_features", None) or {}
        shap_raw = graph_feats.get("shap", {})
        if isinstance(shap_raw, dict):
            return [
                SHAPFeatureItem(name=k, value=v if isinstance(v, (int, float)) else 0.0, shap_value=0.0)
                for k, v in list(shap_raw.items())[:5]
            ]
        return []

    def _extract_graph_nodes(self, layer2_result) -> list[GraphNodeItem]:
        if layer2_result is None:
            return []
        graph_feats = getattr(layer2_result, "graph_features", None) or {}
        nodes_raw = graph_feats.get("graph_nodes", [])
        if isinstance(nodes_raw, list):
            return [
                GraphNodeItem(type=n.get("type", "unknown"), id=str(n.get("id", "?")), importance=float(n.get("importance", 0.0)))
                for n in nodes_raw[:10]
            ]
        return []

    def _build_summary_stats(self, ensemble_result) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        if ensemble_result is None:
            return stats
        l1 = getattr(ensemble_result, "layer1_result", None)
        l2 = getattr(ensemble_result, "layer2_result", None)
        if l1:
            stats["layer1_rules"] = getattr(l1, "triggered_rules", [])
            stats["layer1_decision"] = getattr(l1, "decision", "ALLOW")
        if l2:
            stats["layer2_probability"] = getattr(l2, "fraud_probability", 0.0)
            stats["layer2_source"] = getattr(l2, "source", "L2_GNN")
            graph_feats = getattr(l2, "graph_features", None) or {}
            if isinstance(graph_feats, dict):
                velocity = graph_feats.get("velocity", {})
                if isinstance(velocity, dict):
                    stats["txn_count_5min"] = velocity.get("txn_count_5min", 0)
                    stats["amount_sum_1h"] = velocity.get("amount_sum_1h", 0)
                geo = graph_feats.get("geo", {})
                if isinstance(geo, dict):
                    stats["location_deviation_km"] = geo.get("location_deviation_km", 0)
                benford = graph_feats.get("benford", {})
                if isinstance(benford, dict):
                    stats["benford_chi2"] = benford.get("chi2", 0)
        stats["ensemble_decision"] = getattr(ensemble_result, "decision", "ALLOW")
        stats["ensemble_confidence"] = getattr(ensemble_result, "confidence", 0.0)
        return stats

    @staticmethod
    def _rule_severity(rule: str) -> Literal[1, 2, 3, 4, 5]:
        high = {"BLOCK", "HARD_BLOCK", "CRITICAL"}
        medium = {"ESCALATE", "REVIEW", "SUSPICIOUS"}
        rule_upper = rule.upper()
        for kw in high:
            if kw in rule_upper:
                return 5
        for kw in medium:
            if kw in rule_upper:
                return 3
        return 2
