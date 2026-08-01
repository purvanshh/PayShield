"""Statistical parity and equal opportunity difference on synthetic UPI data.

Demographic slices: gender (male/female), age-tier (young/mid/senior),
city-tier (tier1/tier2/tier3). Uses a simple fraud model with injected bias
per attribute to produce measurable SPD/EOD numbers.

Run:  python models/fairness_audit.py
"""

from collections import defaultdict


def _generate_synthetic_dataset(seed: int = 42) -> list[dict]:
    import numpy as np

    rng = np.random.default_rng(seed)
    records = []
    genders = ["male", "female"]
    age_tiers = ["young", "mid", "senior"]
    city_tiers = ["tier1", "tier2", "tier3"]

    for _ in range(3000):
        gender = rng.choice(genders)
        age_tier = rng.choice(age_tiers)
        city_tier = rng.choice(city_tiers)
        amount = rng.exponential(scale=3000)

        risk = 0.10
        if gender == "male":
            risk += 0.02
        if age_tier == "young":
            risk += 0.015
        elif age_tier == "senior":
            risk -= 0.01
        if city_tier == "tier3":
            risk += 0.025

        tx_risk = min(0.95, risk * (amount / 800 + 1.0) * 0.25)
        is_fraud = rng.random() < tx_risk

        score = min(0.99, max(0.01, risk + rng.normal(scale=0.15) + 0.1 * (amount / 5000)))
        predicted = score >= 0.50

        records.append({
            "gender": gender,
            "age_tier": age_tier,
            "city_tier": city_tier,
            "amount": amount,
            "is_fraud": is_fraud,
            "predicted": predicted,
            "score": score,
        })
    return records


def compute_metrics(records: list[dict], attribute: str) -> dict:
    groups = defaultdict(list)
    for r in records:
        groups[r[attribute]].append(r)

    metrics = {}
    for group, items in sorted(groups.items()):
        n = len(items)
        fraud_rate = sum(1 for r in items if r["is_fraud"]) / n if n else 0
        positive_rate = sum(1 for r in items if r["predicted"]) / n if n else 0
        tp = sum(1 for r in items if r["is_fraud"] and r["predicted"])
        fn = sum(1 for r in items if r["is_fraud"] and not r["predicted"])
        tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        metrics[group] = {
            "count": n,
            "fraud_rate": round(fraud_rate, 4),
            "positive_rate": round(positive_rate, 4),
            "tpr": round(tpr, 4),
        }
    return metrics


def compute_spd(metrics: dict) -> float:
    groups = list(metrics.keys())
    if len(groups) < 2:
        return 0.0
    pos_rates = [m["positive_rate"] for m in metrics.values()]
    return round(max(pos_rates) - min(pos_rates), 4)


def compute_eod(metrics: dict) -> float:
    groups = list(metrics.keys())
    if len(groups) < 2:
        return 0.0
    tprs = [m["tpr"] for m in metrics.values()]
    return round(max(tprs) - min(tprs), 4)


def run_audit():
    records = _generate_synthetic_dataset()
    report = {}
    for attr in ["gender", "age_tier", "city_tier"]:
        m = compute_metrics(records, attr)
        report[attr] = {
            "metrics": m,
            "spd": compute_spd(m),
            "eod": compute_eod(m),
        }
    return report


def print_report(report: dict):
    print("=" * 68)
    print("  PayShield Fairness Audit — SPD / EOD on Synthetic Slices")
    print("=" * 68)
    for attr, data in report.items():
        print(f"\n{attr.upper()} SLICES")
        print(f"  SPD (Δ positive-rate): {data['spd']:.4f}  "
              f"| EOD (Δ true-positive-rate): {data['eod']:.4f}")
        print(f"  {'Group':<10} {'Count':>6} {'Fraud%':>8} {'Pred%':>8} {'TPR':>8}")
        for group, m in data["metrics"].items():
            print(
                f"  {group:<10} {m['count']:>6} "
                f"{m['fraud_rate']*100:>7.2f}% {m['positive_rate']*100:>7.2f}% "
                f"{m['tpr']:>8.4f}"
            )
    print()

    worst_spd = max(v["spd"] for v in report.values())
    worst_eod = max(v["eod"] for v in report.values())
    verdict = (
        "PASS — all slices within acceptable bias thresholds."
        if worst_spd < 0.15 and worst_eod < 0.15
        else "REVIEW — at least one slice exceeds fairness threshold (|SPD| or |EOD| >= 0.15)."
    )
    print(f"WORST SPD: {worst_spd:.4f}, WORST EOD: {worst_eod:.4f}")
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    report = run_audit()
    print_report(report)
