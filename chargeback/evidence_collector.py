"""Chargeback Evidence Collector (Track 02 - Phase 9).

Pulls evidence from PayShield's L1/L2/L3 layers and (optionally) merchant
data to assemble a complete evidence bundle for dispute rebuttal.

Read-only retrieval: all analysis was done at transaction time; this module
reconstructs what the pipeline *knew then* from the tamper-evident audit
chain, the Redis feature mirrors (velocity lists, Benford hashes, device
index) and optional L2/L3 providers. It never re-runs analysis - a rebuttal
must reflect point-in-time state, not hindsight.
"""

import json
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from api.schemas.chargeback import (
    AuditLogEntry,
    BenfordEvidence,
    DeviceFingerprint,
    EvidenceBundle,
    GeoEvidence,
    GraphEvidence,
    InvestigationReport,
    TransactionProof,
    VelocityEvidence,
)
from chargeback.exceptions import ChargebackTransactionNotFoundError

logger = logging.getLogger(__name__)

try:
    from engine.statistical_filter import benford_chi2

    _benford_available = True
except ImportError:  # pragma: no cover - benford_chi2 ships with engine
    _benford_available = False


def _as_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


class ChargebackEvidenceCollector:
    """Collects all evidence for a chargeback rebuttal from PayShield layers.

    Args:
        redis: async Redis client (velocity lists, Benford hashes, device index).
        audit_reader: :class:`store.audit_log.AuditLogReader` (JSONL chain).
        statistical_filter: injected for interface parity; rules were already
            evaluated at txn time, this module does not invoke it.
        gnn_engine: optional object exposing ``get_graph_evidence(txn_id, record)``.
        llm_investigator: optional object exposing ``get_report(txn_id)``.
        merchant_evidence_provider: optional async callable
            ``(transaction_id, dispute_id) -> dict | None`` returning a
            merchant-evidence mapping (delivery_proof, communication...) used
            by the API layer (Phase 11 razorpay client wiring).
    """

    def __init__(
        self,
        redis=None,
        audit_reader=None,
        statistical_filter=None,
        gnn_engine: Any | None = None,
        llm_investigator: Any | None = None,
        merchant_evidence_provider: Callable[..., Awaitable[dict | None]] | None = None,
        explanation_dir: str = "models/production/explanations",
    ):
        self.redis = redis
        self.audit_reader = audit_reader
        self.statistical_filter = statistical_filter
        self.gnn_engine = gnn_engine
        self.llm_investigator = llm_investigator
        self.merchant_evidence_provider = merchant_evidence_provider
        self.explanation_dir = explanation_dir

    async def collect_evidence(
        self,
        transaction_id: str,
        dispute_id: str = "",
    ) -> EvidenceBundle:
        """Collect available evidence for a transaction.

        Raises:
            ChargebackTransactionNotFoundError: txn missing from the audit chain.
        """
        evidence = EvidenceBundle()
        audit_trail: list[AuditLogEntry] = []

        txn_record = await self._load_txn_record(transaction_id)
        if not txn_record:
            raise ChargebackTransactionNotFoundError(
                f"Transaction {transaction_id} not found in audit log"
            )

        # === Step 1: reconstruct the L1 snapshot (rules already fired + counts)
        evidence.velocity_evidence = self._collect_l1_velocity(txn_record)
        evidence.geo_evidence = self._collect_l1_geo(txn_record)
        evidence.benford_evidence = await self._collect_l1_benford(txn_record)
        audit_trail.append(
            AuditLogEntry(
                timestamp=datetime.now(UTC),
                action="L1_EVIDENCE_COLLECTED",
                agent="transaction_agent",
                detail=f"rules={txn_record.get('triggered_rules', [])}",
            )
        )

        # === Step 2: L2 graph evidence (stored at txn time, not recomputed)
        graph = await self._collect_l2_evidence(txn_record)
        if graph is not None:
            evidence.graph_evidence = graph
            audit_trail.append(
                AuditLogEntry(
                    timestamp=datetime.now(UTC),
                    action="L2_GRAPH_ANALYZED",
                    agent="graph_model",
                    detail=f"gnn_score={graph.gnn_score}",
                )
            )

        # === Step 3: L3 investigation report (may have not completed)
        l3 = await self._collect_l3_report(txn_record)
        if l3 is not None:
            evidence.investigation_report = l3
            audit_trail.append(
                AuditLogEntry(
                    timestamp=datetime.now(UTC),
                    action="L3_NARRATIVE_GENERATED",
                    agent="llm_investigator",
                    detail=f"quality={l3.quality_score}",
                )
            )

        # === Step 4: transaction proof from the audit record
        evidence.transaction_proof = self._build_transaction_proof(txn_record)

        # === Step 5: device and IP evidence
        evidence.device_fingerprint = await self._get_device_evidence(txn_record)
        if evidence.device_fingerprint is None:
            audit_trail.append(
                AuditLogEntry(
                    timestamp=datetime.now(UTC),
                    action="DEVICE_LOOKUP_MISSED",
                    agent="transaction_agent",
                    detail="device not in index",
                )
            )

        # === Step 6: merchant-provided evidence (delivery proof, comms, policy)
        if self.merchant_evidence_provider is not None:
            try:
                merchant = await self.merchant_evidence_provider(transaction_id, dispute_id)
                if merchant:
                    from api.schemas.chargeback import MerchantEvidence

                    evidence.merchant_evidence = MerchantEvidence.model_validate(merchant)
                    audit_trail.append(
                        AuditLogEntry(
                            timestamp=datetime.now(UTC),
                            action="MERCHANT_EVIDENCE_COLLECTED",
                            agent="merchant_api",
                            detail="delivery/comms evidence merged",
                        )
                    )
            except Exception as e:
                logger.warning("merchant evidence fetch failed: %s", e)

        # === Step 7: completeness and audit trail
        evidence.audit_trail = audit_trail
        evidence.completeness_score = self._calculate_completeness(evidence)
        return evidence

    # ------------------------------------------------------------------ #
    # retrieval helpers (never re-scoring)                               #
    # ------------------------------------------------------------------ #

    async def _load_txn_record(self, transaction_id: str) -> dict[str, Any] | None:
        """Resolve the audit entry for a txn into a flat feature record."""
        entry = None
        if self.audit_reader is not None:
            entry = await self._async_get_transaction(transaction_id)
        if entry is None:
            return self._try_explanation_artifact(transaction_id)

        payload = entry.get("payload", {})
        record: dict[str, Any] = {
            "txn_id": payload.get("txn_id", transaction_id),
            "user_id": entry.get("actor", ""),
            "merchant_id": payload.get("merchant_id", ""),
            "amount": payload.get("amount", 0.0),
            "device_fingerprint": payload.get("device_fingerprint", ""),
            "decision": entry.get("decision", "ALLOW"),
            "timestamp": entry.get("timestamp", ""),
            "fraud_probability": payload.get("fraud_probability", 0.0),
            "layer_triggered": payload.get("layer_triggered", "L1_STATISTICAL"),
            "triggered_rules": list(payload.get("triggered_rules", [])),
            "audit_entry_id": entry.get("entry_id", ""),
        }
        record.update(await self._read_redis_l1(record))
        return record

    async def _async_get_transaction(self, transaction_id: str) -> dict | None:
        getter = getattr(self.audit_reader, "get_transaction", None)
        if getter is None:
            return None
        result = getter(transaction_id)
        if isinstance(result, dict):
            return result
        if isinstance(result, Awaitable):
            return await result
        return None

    def _try_explanation_artifact(self, transaction_id: str) -> dict[str, Any] | None:
        """Fall back to the persisted L1 explanation artifact.

        ``api/routes/score.py::_persist_explanation`` writes one JSON per
        blocked/reviewed txn - the best point-in-time record for those.
        """
        path = os.path.join(self.explanation_dir, f"{transaction_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                artifact = json.load(f)
            return {
                "txn_id": transaction_id,
                "user_id": "",
                "merchant_id": artifact.get("merchant_id", ""),
                "amount": artifact.get("amount", 0.0),
                "device_fingerprint": artifact.get("device_fingerprint", ""),
                "decision": artifact.get("decision", "REVIEW"),
                "timestamp": artifact.get("generated_at", ""),
                "fraud_probability": artifact.get("fraud_probability", 0.0),
                "layer_triggered": artifact.get("explanation_source", "L1_STATISTICAL"),
                "triggered_rules": list(artifact.get("triggered_rules", [])),
                "rule_details": list(artifact.get("rule_details", [])),
                "velocity_features": artifact.get("velocity_features", {}),
                "audit_entry_id": "",
            }
        except Exception as e:
            logger.warning("explanation artifact unreadable: %s", e)
            return None

    async def _read_redis_l1(self, record: dict[str, Any]) -> dict[str, Any]:
        """Refresh velocity counts from the Redis mirrors (best-effort)."""
        user_id = record.get("user_id", "")
        if not user_id or self.redis is None:
            return {}
        out: dict[str, Any] = {}
        txn_epoch = 0.0
        try:
            txn_ts = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
            txn_epoch = txn_ts.timestamp()
        except Exception:
            txn_epoch = 0.0
        try:
            raw = await self.redis.lrange(f"velocity:user:{user_id}", 0, -1)
            entries = []
            for line in raw:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
            past = [e for e in entries if e.get("ts", 0) < txn_epoch - 1] if txn_epoch else entries
            out["txn_count_5m"] = sum(1 for e in past if e.get("ts", 0) >= txn_epoch - 300)
            out["txn_count_1h"] = sum(1 for e in past if e.get("ts", 0) >= txn_epoch - 3600)
            out["amount_total_1h"] = round(
                sum(float(e.get("amount", 0)) for e in past if e.get("ts", 0) >= txn_epoch - 3600), 2
            )
        except Exception as e:
            logger.debug("velocity mirror read failed: %s", e)
        return out

    def _collect_l1_velocity(self, record: dict[str, Any]) -> VelocityEvidence:
        rules = [r for r in record.get("triggered_rules", []) if r.startswith("V-")]
        count_5m = int(record.get("txn_count_5m", 0))
        count_1h = int(record.get("txn_count_1h", 0))
        amount_1h = _as_decimal(record.get("amount_total_1h", 0))
        if count_5m or count_1h:
            explanation = f"User performed {count_1h} transactions in 1 hour totalling Rs.{amount_1h}"
        elif rules:
            explanation = f"Velocity rules fired: {', '.join(rules)}"
        else:
            explanation = (
                "No velocity rules fired at transaction time; "
                "activity within user baseline"
            )
        return VelocityEvidence(
            rules_triggered=rules,
            txn_count_5m=count_5m,
            txn_count_1h=count_1h,
            amount_total_1h=amount_1h,
            explanation=explanation,
        )

    def _collect_l1_geo(self, record: dict[str, Any]) -> GeoEvidence:
        rules = [r for r in record.get("triggered_rules", []) if r.startswith("G-")]
        if rules:
            explanation = f"Geographic rules fired: {', '.join(rules)}"
        else:
            explanation = (
                "Geographic checks passed; no location anomaly "
                "flagged at transaction time"
            )
        return GeoEvidence(rules_triggered=rules, explanation=explanation)

    async def _collect_l1_benford(
        self, record: dict[str, Any]
    ) -> BenfordEvidence | None:
        merchant_id = record.get("merchant_id", "")
        rules = [r for r in record.get("triggered_rules", []) if r.startswith("B-")]
        counts: list[int] = []
        total = 0
        chi2_statistic: float | None = None
        if merchant_id and self.redis is not None:
            try:
                data = await self.redis.hgetall(f"benford:{merchant_id}")
                if data:
                    counts = [int(data.get(str(d), 0)) for d in range(1, 10)]
                    total = int(data.get("total", 0) or sum(counts))
                    if _benford_available and total >= 20:
                        chi2_statistic = float(benford_chi2(counts))
            except Exception as e:
                logger.debug("benford mirror read failed: %s", e)
        if not rules and not total:
            return None
        return BenfordEvidence(
            rules_triggered=rules,
            chi2_statistic=round(chi2_statistic, 3) if chi2_statistic is not None else None,
            observed_counts=counts,
            total_transactions=total,
            is_anomalous=bool(rules or (chi2_statistic or 0) > 15.51),
            explanation=(
                f"Benford chi2={chi2_statistic:.2f} for merchant {merchant_id}"
                if chi2_statistic is not None
                else f"Benford rules fired for merchant {merchant_id}: {', '.join(rules)}"
            ),
        )

    async def _collect_l2_evidence(
        self, txn_record: dict[str, Any]
    ) -> GraphEvidence | None:
        if self.gnn_engine is None:
            return None
        fetcher = getattr(self.gnn_engine, "get_graph_evidence", None)
        if fetcher is None:
            return None
        try:
            data = fetcher(txn_record.get("txn_id"), txn_record)
            if isinstance(data, Awaitable):
                data = await data
            if not data:
                return None
            if isinstance(data, GraphEvidence):
                return data
            return GraphEvidence.model_validate(data)
        except Exception as e:
            logger.warning("graph evidence fetch failed: %s", e)
            return None

    async def _collect_l3_report(
        self, txn_record: dict[str, Any]
    ) -> InvestigationReport | None:
        if self.llm_investigator is None:
            return None
        getter = getattr(self.llm_investigator, "get_report", None)
        if getter is None:
            return None
        try:
            data = getter(txn_record.get("txn_id"))
            if isinstance(data, Awaitable):
                data = await data
            if not data:
                return None
            if isinstance(data, InvestigationReport):
                return data
            return InvestigationReport.model_validate(data)
        except Exception as e:
            logger.warning("l3 report fetch failed: %s", e)
            return None

    def _build_transaction_proof(self, record: dict[str, Any]) -> TransactionProof:
        return TransactionProof(
            txn_timestamp=datetime.fromisoformat(
                record["timestamp"].replace("Z", "+00:00")
            )
            if isinstance(record.get("timestamp"), str) and record.get("timestamp")
            else datetime.now(UTC),
            amount=_as_decimal(record.get("amount", 0)),
            currency="INR",
            payment_method="UPI",
            merchant_id=record.get("merchant_id", ""),
            was_blocked=record.get("decision") == "BLOCK",
        )

    async def _get_device_evidence(
        self, record: dict[str, Any]
    ) -> DeviceFingerprint | None:
        device_id = record.get("device_fingerprint", "")
        if not device_id:
            return None
        if self.redis is None:
            return DeviceFingerprint(device_id=device_id, is_new_device=True)

        # The audit chain masks device ids (PCI compliance) - resolve the real
        # id through the user->device index when it is unavailable directly.
        candidates = [device_id]
        if "*" in device_id:
            user_id = record.get("user_id", "")
            if user_id:
                try:
                    candidates = sorted(await self.redis.smembers(f"ud:{user_id}")) or candidates
                except Exception as e:
                    logger.debug("user device index read failed: %s", e)

        for candidate in candidates:
            fp = await self._lookup_device_index(candidate)
            if fp is not None:
                fp.device_id = fp.device_id or candidate
                return fp
        return DeviceFingerprint(device_id=device_id, is_new_device=True)

    async def _lookup_device_index(
        self, device_id: str
    ) -> DeviceFingerprint | None:
        try:
            data = await self.redis.hgetall(f"dfp:{device_id}")
            if not data:
                return None

            def _first_feature(prefix: str) -> str:
                for feat in json.loads(data.get("features", "[]")):
                    if feat.startswith(prefix):
                        return feat[len(prefix):]
                return ""

            return DeviceFingerprint(
                device_id=device_id,
                user_id=data.get("user_id", ""),
                ip_address=_first_feature("ip:"),
                user_agent=data.get("user_agent", ""),
                screen_resolution=_first_feature("screen:"),
                timezone=_first_feature("tz:"),
                language=_first_feature("lang:"),
                canvas_hash=data.get("canvas_hash", ""),
                webgl_hash=data.get("webgl_hash", ""),
                first_seen=_parse_dt(data.get("first_seen")),
                last_seen=_parse_dt(data.get("last_seen")),
                is_new_device=False,
            )
        except Exception as e:
            logger.debug("device lookup failed: %s", e)
            return None

    def _calculate_completeness(self, evidence: EvidenceBundle) -> float:
        """Point-in-time bundle coverage in [0, 1]."""
        required = [
            evidence.transaction_proof is not None,
            evidence.device_fingerprint is not None,
        ]
        optional = [
            evidence.velocity_evidence is not None,
            evidence.geo_evidence is not None,
            evidence.benford_evidence is not None,
            evidence.graph_evidence is not None,
            evidence.investigation_report is not None,
        ]
        base_score = sum(required) / len(required)
        bonus = sum(optional) / len(optional) * 0.3
        return round(min(1.0, base_score + bonus), 4)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
