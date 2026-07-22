import argparse
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from data.synthetic_upi import SyntheticUPIGenerator
from store.redis_client import RedisClient
from store.feature_store import FeatureStore
from store.graph_db import GraphDB
from engine.ensemble import EnsembleScorer


def compute_fvar(df: pd.DataFrame, results: list[dict], avg_fraud_value: float = 15000.0, fp_cost: float = 50.0) -> dict:
    true_fraud = df["is_fraud"].values
    pred_fraud = np.array([r["decision"] == "BLOCK" for r in results])

    tp = (true_fraud & pred_fraud).sum()
    fp = (~true_fraud & pred_fraud).sum()
    fn = (true_fraud & ~pred_fraud).sum()

    prevented_loss = tp * avg_fraud_value
    fp_penalty = fp * fp_cost
    missed_loss = fn * avg_fraud_value

    return {
        "fvar_inr": round(prevented_loss - fp_penalty - missed_loss, 2),
        "prevented_loss_inr": round(prevented_loss, 2),
        "fp_penalty_inr": round(fp_penalty, 2),
        "missed_loss_inr": round(missed_loss, 2),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "precision": float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0,
        "recall": float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--daily-txns", type=int, default=2000)
    parser.add_argument("--users", type=int, default=2000)
    parser.add_argument("--merchants", type=int, default=500)
    parser.add_argument("--fraud-ratio", type=float, default=0.05)
    args = parser.parse_args()

    total_txns = args.days * args.daily_txns
    print(f"Backtesting: {args.days} days, {total_txns} transactions...")

    gen = SyntheticUPIGenerator(
        n_users=args.users,
        n_merchants=args.merchants,
        n_transactions=total_txns,
        fraud_ratio=args.fraud_ratio,
    )
    df = gen.generate()
    df = df.sort_values("timestamp").reset_index(drop=True)

    redis = RedisClient()
    feature_store = FeatureStore(redis)
    graph_db = GraphDB()
    ensemble = EnsembleScorer(graph_db)

    results = []
    batch_size = 100
    start_time = time.time()

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i : i + batch_size]
        for _, txn in batch.iterrows():
            txn_ts = txn["timestamp"].timestamp() if isinstance(txn["timestamp"], datetime) else txn["timestamp"]
            feature_store.increment_velocity_counter(txn["user_id"], txn_ts)
            feature_store.set_device_fingerprint(txn["device_fingerprint"], txn["user_id"])
            feature_store.set_geospatial_cache(txn["user_id"], txn["lat"], txn["lon"], txn_ts)
            result = ensemble.score(txn.to_dict(), feature_store)
            results.append(result)

        if (i // batch_size) % 50 == 0:
            elapsed = time.time() - start_time
            pct = (i / total_txns) * 100
            rate = i / elapsed if elapsed > 0 else 0
            print(f"  {pct:.0f}% | {i}/{total_txns} | {rate:.0f} txns/s")

    total_elapsed = time.time() - start_time
    print(f"\nProcessed {total_txns} transactions in {total_elapsed:.1f}s ({total_txns/total_elapsed:.0f} txns/s)")

    fvar = compute_fvar(df, results)
    total_fraud_value = df["is_fraud"].sum() * 15000
    print(f"\n{'─' * 55}")
    print(f"Backtest Results — {args.days} Days, {total_txns} Transactions")
    print(f"{'─' * 55}")
    print(f"  Fraud transactions:     {df['is_fraud'].sum()}")
    print(f"  Total fraud value:      ₹{total_fraud_value:,.2f}")
    print(f"  True Positives:         {fvar['true_positives']}")
    print(f"  False Positives:        {fvar['false_positives']}")
    print(f"  False Negatives:        {fvar['false_negatives']}")
    print(f"  Precision:              {fvar['precision']:.4f}")
    print(f"  Recall:                 {fvar['recall']:.4f}")
    print(f"  Prevented loss:         ₹{fvar['prevented_loss_inr']:,.2f}")
    print(f"  FP penalty:             ₹{fvar['fp_penalty_inr']:,.2f}")
    print(f"  Missed loss:            ₹{fvar['missed_loss_inr']:,.2f}")
    print(f"  FVaR:                   ₹{fvar['fvar_inr']:,.2f}")
    print(f"{'─' * 55}")
    print(f"  Monthly FVaR projection: ₹{fvar['fvar_inr'] * 30 / args.days:,.2f}")
    print(f"{'─' * 55}")

    redis.close()


if __name__ == "__main__":
    main()
