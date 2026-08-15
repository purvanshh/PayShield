"""Continuous-improvement gate: is the benchmarked candidate better than the
currently promoted model?

Reused by ``make retrain`` and ``.github/workflows/retrain.yml``. The candidate
is the JSON written by ``scripts/benchmark_gnn.py`` (nested
``gnn.test_metrics.auc_pr`` layout; flat ``gnn.auc_pr`` also accepted). The
baseline is read from the registry latest version (``metadata.json`` with a
``manifest.json`` fallback), or from ``models/gnn_benchmark_results_original.json``
when no version is registered yet.

Exit codes:
    0  improved (and, with --register-if-better, registered + promoted)
    1  NOT improved — production left untouched
    2  could not evaluate (missing candidate/baseline data)

Usage:
    python scripts/check_improvement.py [--candidate models/gnn_benchmark_results.json]
                                        [--registry-root models/registry]
                                        [--metric auc_pr] [--epsilon 0.005]
                                        [--register-if-better]
"""

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = Path("configs/train_config_retrain.yaml")


def load_config() -> dict:
    gate = {"metric": "auc_pr", "epsilon": 0.005}
    if DEFAULT_CONFIG.exists():
        try:
            with open(DEFAULT_CONFIG) as f:
                data = yaml.safe_load(f) or {}
            gate.update(data.get("gate", {}))
        except Exception as e:
            logger.warning(f"retrain config load failed: {e}")
    return gate


def extract_metric(results: dict, metric: str) -> float | None:
    """Read a metric from the benchmark results JSON (nested or flat layout)."""
    gnn = results.get("gnn", {})
    if "test_metrics" in gnn and metric in gnn["test_metrics"]:
        return float(gnn["test_metrics"][metric])
    if metric in gnn:
        return float(gnn[metric])
    if metric in results:
        return float(results[metric])
    return None


def baseline_from_registry(registry_root: Path) -> float | None:
    latest = registry_root / "latest"
    if not latest.exists():
        return None
    version_dir = latest.resolve()
    metadata = version_dir / "metadata.json"
    candidates = [metadata, version_dir / "manifest.json"]
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(Path(path).read_text())
            except (json.JSONDecodeError, OSError):
                continue
            for key in ("pr_auc", "auc_pr"):
                if key in data:
                    return float(data[key])
            metrics = data.get("metrics", {})
            for key in ("auc_pr", "pr_auc", "test_auc_pr"):
                if key in metrics:
                    return float(metrics[key])
    return None


def write_decision_log(status: str, candidate: float | None, baseline: float | None,
                       epsilon: float, version: str | None, path: Path):
    decision = {
        "status": status,
        "metric": "auc_pr",
        "candidate_pr_auc": candidate,
        "baseline_pr_auc": baseline,
        "delta": round(candidate - baseline, 4) if candidate is not None and baseline is not None else None,
        "epsilon": epsilon,
        "registered_version": version,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decision, indent=2))
    print(f"decision log: {path}")


def register_and_promote(results: dict, registry_root: Path) -> str:
    """Register the candidate checkpoint into the registry and promote it.

    Mirrors the v1.1.0 registration conventions: ModelRegistry.register(),
    --production promote, registry/latest symlink, metadata.json with the
    full metrics/hyperparameters snapshot.
    """
    from ml.registry import ModelRegistry

    registry = ModelRegistry(base_dir=str(registry_root.parent))

    artifact_dir = Path("models/production")
    checkpoint = artifact_dir / "payshield_gnn_v1.pt"
    if not checkpoint.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint}")

    gnn = results.get("gnn", {})
    hyperparameters = gnn.get("hyperparameters", {})
    metrics = {
        "auc_pr": extract_metric(results, "auc_pr"),
        "auc_roc": extract_metric(results, "auc_roc"),
        "fpr_at_0.90_recall": (gnn.get("test_metrics") or {}).get("fpr_at_0.90_recall"),
        "parameters": gnn.get("parameters"),
        "inference_p99_ms": (gnn.get("inference_latency_ms_cpu") or {}).get("p99_ms"),
    }
    metrics = {k: v for k, v in metrics.items() if v is not None}

    version = registry.register(
        checkpoint,
        metrics=metrics,
        hyperparameters=hyperparameters,
        dataset_version=str((results.get("data") or {}).get("seed", "unknown")),
    )
    registry.promote(version, "production")

    version_dir = registry_root / version
    shutil_copy(checkpoint, version_dir / "payshield_gnn_v1.pt")

    metadata = {
        "version": version,
        "release_date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "pr_auc": extract_metric(results, "auc_pr"),
        "roc_auc": extract_metric(results, "auc_roc"),
        "fpr_at_90_recall": (gnn.get("test_metrics") or {}).get("fpr_at_0.90_recall"),
        "parameters": gnn.get("parameters"),
        "inference_p99_ms": (gnn.get("inference_latency_ms_cpu") or {}).get("p99_ms"),
        "hyperparameters": hyperparameters,
        "features": {
            "user": ["credit_score", "account_age_days", "kyc_tier", "avg_monthly_txn_count", "device_count"],
            "merchant": ["mcc_one_hot (15)", "avg_txn_amount", "refund_rate", "account_age_days", "city_tier", "is_shell", "round_amount_share"],
            "device": ["os_family", "app_version_major", "app_version_minor", "is_emulator"],
            "transaction": ["amount", "hour", "weekend", "salary_day", "inter_arrival_gap", "txn_count_5m", "txn_count_1h", "location_distance"],
        },
        "training_data": {
            "users": (results.get("data") or {}).get("users"),
            "merchants": (results.get("data") or {}).get("merchants"),
            "txns": (results.get("data") or {}).get("transactions"),
            "fraud_rate": (results.get("data") or {}).get("fraud_ratio"),
            "seed": (results.get("data") or {}).get("seed"),
            "split": "user-disjoint 80/10/10",
        },
        "model_card": "model_card.md",
        "checkpoint": "payshield_gnn_v1.pt",
        "registry_filename": "model.pt",
    }
    (version_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    latest_link = registry_root / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(version_dir.name)
    print(f"registered: {version} (registry/latest -> {version_dir.name})")
    return version


def shutil_copy(src: Path, dst: Path):
    import shutil

    if src.exists():
        shutil.copy2(str(src), str(dst))


def main() -> int:
    ap = argparse.ArgumentParser(description="Candidate-vs-production improvement gate")
    ap.add_argument("--candidate", default="models/gnn_benchmark_results.json",
                    help="benchmark results JSON from scripts/benchmark_gnn.py")
    ap.add_argument("--registry-root", default="models/registry")
    ap.add_argument("--metric", default="", help="gate metric (default: from retrain config)")
    ap.add_argument("--epsilon", type=float, default=None,
                    help="minimum improvement delta (default: from retrain config, 0.005)")
    ap.add_argument("--register-if-better", action="store_true",
                    help="register + promote the candidate when it clears the gate")
    ap.add_argument("--decision-log", default="models/retrain_decision.json")
    args = ap.parse_args()

    config = load_config()
    metric = args.metric or config["metric"]
    epsilon = args.epsilon if args.epsilon is not None else float(config["epsilon"])

    candidate_path = Path(args.candidate)
    if not candidate_path.exists():
        print(f"ERROR: candidate results not found: {candidate_path}", file=sys.stderr)
        return 2
    results = json.loads(candidate_path.read_text())

    candidate = extract_metric(results, metric)
    if candidate is None:
        print(f"ERROR: metric '{metric}' missing from {candidate_path}", file=sys.stderr)
        return 2

    baseline = baseline_from_registry(Path(args.registry_root))
    if baseline is None:
        original = Path("models/gnn_benchmark_results_original.json")
        if original.exists():
            o = json.loads(original.read_text())
            baseline = extract_metric(o, metric)
        else:
            print("WARNING: no registered model and no original baseline — treating candidate as improved")
            baseline = 0.0

    delta = candidate - baseline
    improved = delta >= epsilon
    status = "IMPROVED" if improved else "NOT_IMPROVED"
    print(f"candidate {metric}: {candidate}")
    print(f"baseline  {metric}: {baseline}")
    print(f"delta: {delta:+.4f} (gate epsilon {epsilon}) -> {status}")

    version = None
    if improved and args.register_if_better:
        version = register_and_promote(results, Path(args.registry_root))

    write_decision_log(status, candidate, baseline, epsilon, version, Path(args.decision_log))
    return 0 if improved else 1


if __name__ == "__main__":
    sys.exit(main())
