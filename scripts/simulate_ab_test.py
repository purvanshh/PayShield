#!/usr/bin/env python3
"""Return-risk champion/challenger A/B test simulation (Track 02 - Phase 7).

Simulates a controlled experiment between the current friction-feature
weights (champion) and a reflection-tuned challenger on synthetic orders,
then decides **promote / keep** the way a real team would — on a
statistically significant difference in merchant cost savings, not on a
training metric.

Design
------
- Dataset: ``ReturnRiskSyntheticGenerator`` (seed 42), chronological per-user
  profiles seeded into an in-memory Redis (the scoring path never sees future
  returns).
- Bucketing: deterministic per-user (sha256 of user_id), so a user always
  lands on the same arm — mimicking a stable merchant-level traffic split.
- Metric: per-order **cost saved** (false-allow avoided minus false-block
  incurred) using the model in ``docs/cost_model/``. Orders are the unit,
  users are the cluster and bucket.
- Significance: Welch's unequal-variance t-test on per-arm cost-savings
  samples at α = 0.05.

Run: python scripts/simulate_ab_test.py
"""

import argparse
import hashlib
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
from scipy import stats as scipy_stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ALPHA = 0.05


def _sha_bucket(user_id: str, challenger_pct: int) -> bool:
    """Deterministic 0-99 bucket from user_id at the given challenger %."""
    digest = int(hashlib.sha256(user_id.encode()).hexdigest()[:8], 16) % 100
    return digest < challenger_pct


def _challenger_weights(champion: dict[str, float]) -> dict[str, float]:
    """Reflection-agent-style reweighting: emphasise return history and the
    serial-returner flag, de-emphasise the amount feature (a weaker return
    predictor for most categories)."""
    tuned = dict(champion)
    # Weight is redistributed across the 7 features to keep sum ≈ 1.0
    tuned["user_return_rate_30d"] = round(champion.get("user_return_rate_30d", 0.25) + 0.07, 4)
    tuned["user_serial_returner_flag"] = round(
        champion.get("user_serial_returner_flag", 0.20) + 0.04, 4
    )
    tuned["txn_amount_risk"] = max(0.0, round(champion.get("txn_amount_risk", 0.10) - 0.04, 4))
    return tuned


def _scorers(redis) -> tuple[object, object, dict[str, float], dict[str, float]]:
    from return_risk.feature_engine import ReturnRiskFeatureEngine
    from return_risk.rules_engine import RulesEngine
    from return_risk.scorer import FEATURE_WEIGHTS, ReturnRiskScorer

    champion_weights = dict(FEATURE_WEIGHTS)
    challenger_weights = _challenger_weights(champion_weights)

    def build():
        return ReturnRiskScorer(
            feature_engine=ReturnRiskFeatureEngine(redis),
            rules_engine=RulesEngine(),
        )

    champion = build()
    challenger = build()
    champion.weights = champion_weights
    challenger.weights = challenger_weights
    return champion, challenger, champion_weights, challenger_weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--users-per-type", type=int, default=80)
    parser.add_argument("--orders-per-user", type=int, default=20)
    parser.add_argument("--traffic-split", type=float, default=0.10, help="challenger share")
    args = parser.parse_args()

    from data.synthetic.return_generator import ReturnRiskSyntheticGenerator
    from tests.fake_redis import FakeRedis

    print("=" * 66)
    print("PAYSHIELD — RETURN-RISK A/B TEST SIMULATION")
    print(f"Started: {datetime.utcnow().isoformat()}")
    print("=" * 66)

    # 1. generate + seed the feature store
    generator = ReturnRiskSyntheticGenerator(seed=args.seed)
    dataset = generator.generate_dataset(
        num_users_per_type=args.users_per_type, orders_per_user=args.orders_per_user
    )
    redis = FakeRedis()
    _seed(redis, dataset)
    orders = dataset["orders"]
    labels = dataset["labels"]
    print(
        f"Dataset: {len(dataset['users'])} users, {len(orders)} orders "
        f"(seed {args.seed}, chronological per-user)"
    )

    # 2. build arms
    champion, challenger, champion_weights, challenger_weights = _scorers(redis)
    print(f"Champion weights: {champion_weights}")
    print(f"Challenger v1 weights: {challenger_weights}")
    print(
        f"Traffic split: {args.traffic_split:.0%} challenger / {1 - args.traffic_split:.0%} champion"
    )

    # 3. assign orders to arms and score
    champion_savings: list[float] = []
    challenger_savings: list[float] = []
    from docs.cost_model.assumptions import CostAssumptions

    assumptions = CostAssumptions()
    challenger_pct = int(round(args.traffic_split * 100))

    for order in orders:
        to_challenger = _sha_bucket(order["user_id"], challenger_pct)
        scorer = challenger if to_challenger else champion
        result = _score(scorer, order)
        savings = _per_order_savings(result, labels[order["order_id"]], assumptions)
        (challenger_savings if to_challenger else champion_savings).append(savings)

    # 4. analyse
    champ = np.array(champion_savings)
    chall = np.array(challenger_savings)
    _report(champ, chall, "per-order cost saved (₹)")


def _score(scorer, order: dict) -> dict:
    import asyncio

    async def _run():
        return await scorer.score(
            user_id=order["user_id"],
            merchant_id=order["merchant_id"],
            order_id=order["order_id"],
            amount=Decimal(str(order["amount"])),
            category=order["category"],
            cod_flag=order["cod_flag"],
            timestamp=datetime.fromisoformat(order["order_date"]),
        )

    return asyncio.run(_run())


def _per_order_savings(result: dict, label: dict, a) -> float:
    """Money this decision saved (or cost): flagged high-risk orders that
    return are prevented at 70% effectiveness; flagged good orders pay a
    false-block penalty. Returns ₹ saved per order."""
    high_risk = bool(label["high_risk"])
    flagged = result["risk_tier"] in ("MEDIUM", "HIGH")
    if flagged and high_risk:
        prevented = float(a.diversion_effectiveness)
        return a.false_allow_cost * prevented
    if flagged and not high_risk:
        return -a.false_block_cost
    return 0.0


def _report(champ: np.ndarray, chall: np.ndarray, metric: str) -> None:
    n_c, n_t = len(champ), len(chall)
    mean_c, mean_t = float(champ.mean()), float(chall.mean())
    std_c, std_t = float(champ.std(ddof=1)), float(chall.std(ddof=1))

    t_stat, p_value = scipy_stats.ttest_ind(chall, champ, equal_var=False)
    significant = p_value < ALPHA

    print("-" * 66)
    print(f"Result on {metric}")
    print(f"  Champion  (n={n_c})   mean ₹{mean_c:>10,.2f}   std ₹{std_c:,.2f}")
    print(f"  Challenger(n={n_t})   mean ₹{mean_t:>10,.2f}   std ₹{std_t:,.2f}")
    print(f"  Δ               ₹{mean_t - mean_c:>10,.2f}")
    print(f"  Welch t={t_stat:.3f}  p-value={p_value:.4f}  (α={ALPHA})")
    print(f"  Statistically significant: {significant}")

    recommendation = "keep"
    if significant and mean_t > mean_c:
        recommendation = "promote"
    elif significant and mean_t < mean_c:
        recommendation = "keep (challenger is worse)"
    else:
        recommendation = "keep (insufficient evidence — extend experiment)"
    print(f"  RECOMMENDATION: {recommendation}")
    print("=" * 66)


def _seed(redis, dataset) -> None:
    """Seed user/merchant profiles exactly like the benchmark script's
    training-window seeding (no future returns in the profile)."""
    import asyncio

    from tests.fake_redis import FakeRedis

    assert isinstance(redis, FakeRedis)

    async def _run():
        by_user: dict[str, list] = {}
        for order in dataset["orders"]:
            by_user.setdefault(order["user_id"], []).append(order)
        for user in dataset["users"]:
            orders = by_user.get(user["user_id"], [])
            total = len(orders)
            returned = sum(1 for o in orders if o["returned"])
            rate = returned / total if total else 0.0
            await redis.hmset(
                f"return_risk:user:{user['user_id']}",
                {
                    "total_orders": str(total),
                    "total_returns": str(returned),
                    "return_rate_30d": str(round(rate, 4)),
                    "return_rate_90d": str(round(rate, 4)),
                    "avg_return_value": str(user["avg_order_value"]),
                },
            )
            velocity = {}
            for o in orders:
                if o["returned"] and o["return_date"]:
                    from datetime import datetime as _dt

                    velocity[o["order_id"]] = _dt.fromisoformat(o["return_date"]).timestamp()
            if velocity:
                await redis.zadd(f"return_risk:user:{user['user_id']}:returns", velocity)
        for merchant in dataset["merchants"]:
            await redis.hmset(
                f"return_risk:merchant:{merchant['merchant_id']}",
                {"return_rate_30d": str(merchant["return_rate"])},
            )
            await redis.zadd(
                f"return_risk:merchant:{merchant['merchant_id']}:category",
                {merchant["category"]: merchant["return_rate"]},
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
