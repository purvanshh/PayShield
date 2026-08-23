#!/usr/bin/env python3
"""In-process micro-benchmark for the Track 2 hot paths (Phase 44).

Measures the two critical paths exactly as the API runs them (excluding the
ASGI/network hop, which is the honest per-endpoint delta:

- return-risk score: seeded store + full scorer pipeline (Redis fakes)
- chargeback build: audit entry + collector + builder + fallback narrative
- narrative with stalled LLM: the 2.0s timeout cap is the tail fix

Run:
    python scripts/profile_endpoints.py [--iterations 300]
"""

import argparse
import json
import sys
import tempfile
import time as _time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fake_redis import FakeRedis


def _pct(values, p):
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * p))
    return ordered[idx]


def _seed_demo():
    from scripts.seed_demo_data import seed_demo_data
    from tests.fake_redis import FakeSyncRedis

    sync = FakeSyncRedis()
    # seed via the sync path then mirror stores into the async fake
    from store.audit_log import AuditLogWriter

    with tempfile.TemporaryDirectory() as tmp:
        seed_demo_data(redis=sync, audit_writer=AuditLogWriter(tmp))
    sync_store = FakeRedis()
    sync_store._store.hashes.update({k: dict(v) for k, v in sync._store.hashes.items()})
    sync_store._store.zsets.update({k: dict(v) for k, v in sync._store.zsets.items()})
    sync_store._store.sets.update({k: set(v) for k, v in sync._store.sets.items()})
    sync_store._store.lists.update({k: list(v) for k, v in sync._store.lists.items()})
    return sync_store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=300)
    args = parser.parse_args()
    n = args.iterations

    import asyncio

    async def run_all():
        results = {}
        redis = _seed_demo()

        from return_risk.feature_engine import ReturnRiskFeatureEngine
        from return_risk.rules_engine import RulesEngine
        from return_risk.scorer import ReturnRiskScorer

        scorer = ReturnRiskScorer(
            feature_engine=ReturnRiskFeatureEngine(redis), rules_engine=RulesEngine()
        )

        score_lat = []
        for _ in range(n):
            t0 = _time.perf_counter()
            await scorer.score(
                user_id="U_SERIAL_001",
                merchant_id="M_FASHION_001",
                order_id="ORD_PROF_1",
                amount=Decimal("5500"),
                category="fashion",
                cod_flag=True,
                timestamp=datetime(2026, 8, 21, 10, 0),
            )
            score_lat.append((_time.perf_counter() - t0) * 1000)
        results["return_risk_score_ms"] = {
            "p50": round(_pct(score_lat, 0.5), 2),
            "p95": round(_pct(score_lat, 0.95), 2),
            "p99": round(_pct(score_lat, 0.99), 2),
        }

        from chargeback.evidence_collector import ChargebackEvidenceCollector
        from chargeback.rebuttal_builder import ChargebackRebuttalBuilder
        from store.audit_log import AuditLogReader, AuditLogWriter

        with tempfile.TemporaryDirectory() as tmp:
            writer = AuditLogWriter(tmp)
            writer.append(
                "SCORE_DECISION",
                "U001",
                "ALLOW",
                {"txn_id": "TXN_PROF_1", "merchant_id": "M001", "amount": 4500.0,
                 "device_fingerprint": "DEV-1", "triggered_rules": []},
            )
            builder = ChargebackRebuttalBuilder(
                evidence_collector=ChargebackEvidenceCollector(
                    redis=redis, audit_reader=AuditLogReader(tmp)
                ),
                llm_client=None,
                config={"confidence_threshold": 0.6},
            )
            build_lat = []
            for _ in range(n):
                t0 = _time.perf_counter()
                await builder.build_rebuttal(
                    dispute_id="disp_PROF",
                    payment_id="pay_PROF",
                    transaction_id="TXN_PROF_1",
                    network="VISA",
                    reason_code="10.4",
                    reason_description="Fraud - Card Not Present",
                    response_deadline=datetime(2026, 9, 20),
                )
                build_lat.append((_time.perf_counter() - t0) * 1000)
            results["chargeback_build_ms"] = {
                "p50": round(_pct(build_lat, 0.5), 2),
                "p95": round(_pct(build_lat, 0.95), 2),
                "p99": round(_pct(build_lat, 0.99), 2),
            }
        return results

    out = asyncio.run(run_all())
    print(json.dumps(out, indent=2))
    with open("reports/perf_optimization.json", "w") as f:
        json.dump({"environment": "in-process (no ASGI/network) hermetic run",
                   "iterations": n, "results": out}, f, indent=2)
    print("saved reports/perf_optimization.json")


if __name__ == "__main__":
    main()
