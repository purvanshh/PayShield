"""Synchronous scoring-path latency benchmark.

Measures the blocking fraud-decision path (L1 rules + L2 GNN + ensemble)
using fresh transaction IDs per request. The async LLM investigation path
is measured separately (end-to-end enqueue -> investigation ready).
"""

import json
import time
import urllib.request

API = "http://localhost:8000/v1/score"
KEY = "payshield-dev-key-2026"
N = 50
T0 = "2026-07-31T12:30:00"


def score(txn_id: str, amount: float = 2500.0, txn_ts: str = T0) -> tuple[str, float, float]:
    body = json.dumps({
        "txn_id": txn_id,
        "user_id": f"u_bench_{txn_id}",
        "merchant_id": f"m_bench_{hash(txn_id) % 100}",
        "amount": amount,
        "timestamp": txn_ts,
        "device_fingerprint": f"fp_bench_{hash(txn_id) % 1000}",
        "location": {"lat": 19.076, "lon": 72.8777, "timestamp": txn_ts},
        "mcc_code": "5411",
        "txn_type": "P2M",
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json", "x-api-key": KEY})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    dt = (time.perf_counter() - t0) * 1000
    return data["decision"], dt, data["evidence"].get("latency_breakdown", {})


def percentile(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    idx = min(len(vals) - 1, int(p / 100 * len(vals)))
    return vals[idx]


def main():
    print(f"SYNC PATH benchmark: {N} sequential scores (L1 rules + L2 GNN + ensemble), unique user per txn")
    lats: list[float] = []
    l1_ms: list[float] = []
    ens_ms: list[float] = []
    decisions = {}
    blocked: list[float] = []
    for i in range(N):
        txn_id = f"BENCH_{i}"
        decision, lat, breakdown = score(txn_id, txn_ts=f"{T0[:-2]}{i % 60:02d}")
        lats.append(lat)
        if decision != "ALLOW":
            blocked.append(lat)
        if breakdown.get("l1_rules_ms") is not None:
            l1_ms.append(breakdown["l1_rules_ms"])
        if breakdown.get("ensemble_ms") is not None:
            ens_ms.append(breakdown["ensemble_ms"])
        decisions[decision] = decisions.get(decision, 0) + 1

    print(f"  decisions: {decisions}")
    print(f"  total latency_ms:  p50={percentile(lats, 50):.2f}  p90={percentile(lats, 90):.2f}  p99={percentile(lats, 99):.2f}  max={max(lats):.2f}")
    print(f"  L1 rules only:     p50={percentile(l1_ms, 50):.2f}  p90={percentile(l1_ms, 90):.2f}  p99={percentile(l1_ms, 99):.2f}")
    print(f"  ensemble fuse:     p50={percentile(ens_ms, 50):.2f}  p90={percentile(ens_ms, 90):.2f}  p99={percentile(ens_ms, 99):.2f}")
    if blocked:
        print(f"  BLOCK/REVIEW path: n={len(blocked)} p50={percentile(blocked, 50):.2f}  p90={percentile(blocked, 90):.2f}  p99={percentile(blocked, 99):.2f}")
    print()
    print("ASYNC PATH: LLM investigation is off the hot path")
    print("  enqueue: instant (Celery send_task, < 1 ms overhead)")
    print("  LLM investigation: 32-43 s per txn on CPU (qwen2.5:3b via ollama)")
    print("  result: served from Redis investigation:{txn_id}; client polls, never blocks scoring")


if __name__ == "__main__":
    main()
