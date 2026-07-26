import argparse
import logging
import statistics
import time

import numpy as np

from engine.ensemble import ConfidenceCalibrator, EnsembleFusionEngine, EnsembleResult, Layer2Result

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def make_l1(decision: str, confidence: float = 0.0, rules: list[str] | None = None):
    return type("L1Result", (), {
        "decision": decision,
        "confidence": confidence,
        "triggered_rules": rules or [],
    })()


def main():
    parser = argparse.ArgumentParser(description="Benchmark ensemble fusion")
    parser.add_argument("--n-evaluations", type=int, default=10000)
    args = parser.parse_args()

    calibrator = ConfidenceCalibrator()
    rng = np.random.default_rng(42)
    train_conf = rng.uniform(0.0, 1.0, 1000)
    train_labels = (train_conf > 0.7).astype(int)
    calibrator.fit(train_conf.tolist(), train_labels.tolist())
    calibrator.save()

    engine = EnsembleFusionEngine(calibrator=calibrator)

    scenarios = [
        ("L1 BLOCK", make_l1("BLOCK", 1.0), Layer2Result(fraud_probability=0.99)),
        ("L1 ALLOW + L2 HIGH", make_l1("ALLOW"), Layer2Result(fraud_probability=0.92)),
        ("L1 ALLOW + L2 LOW", make_l1("ALLOW"), Layer2Result(fraud_probability=0.15)),
        ("L1 ESCALATE + L2 MID", make_l1("ESCALATE", confidence=0.6, rules=["V-RULE-03"]), Layer2Result(fraud_probability=0.75)),
        ("L1 ESCALATE + L2 HIGH", make_l1("ESCALATE", confidence=0.7, rules=["V-RULE-06"]), Layer2Result(fraud_probability=0.85)),
        ("L1 ALLOW + L2 MID", make_l1("ALLOW"), Layer2Result(fraud_probability=0.55)),
    ]

    print(f"\nScenario tests:")
    for name, l1, l2 in scenarios:
        result = engine.fuse(l1, l2)
        print(f"  {name:30s} -> {result.decision:6s} (conf={result.confidence:.3f}, source={result.source})")

    print(f"\nBenchmarking {args.n_evaluations} fusions...")
    latencies = []
    for i in range(args.n_evaluations):
        l1 = make_l1("ALLOW" if i % 3 != 0 else "ESCALATE")
        l2 = Layer2Result(fraud_probability=rng.uniform(0.0, 1.0))
        start = time.perf_counter()
        engine.fuse(l1, l2)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    print(f"\nFusion latency ({args.n_evaluations} runs):")
    print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.6f} ms")
    print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.6f} ms")
    print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.6f} ms")
    print(f"  avg:   {statistics.mean(latencies):.6f} ms")

    print(f"\nDisagreements logged: {len(engine.disagreements)}")
    print("Done.")


if __name__ == "__main__":
    main()
