import argparse
import logging
from pathlib import Path

from data.synthetic.generator import SyntheticUPIGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic UPI transaction data")
    parser.add_argument("--users", type=int, default=10_000, help="Number of users")
    parser.add_argument("--merchants", type=int, default=1_000, help="Number of merchants")
    parser.add_argument("--transactions", type=int, default=50_000, help="Number of transactions")
    parser.add_argument("--fraud-ratio", type=float, default=0.05, help="Fraud ratio (0.0-1.0)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", type=str, default="data/raw/synthetic_transactions.parquet", help="Output path")
    args = parser.parse_args()

    logger.info(f"Generating {args.transactions} transactions ({args.users} users, {args.merchants} merchants)...")

    gen = SyntheticUPIGenerator(
        n_users=args.users,
        n_merchants=args.merchants,
        n_transactions=args.transactions,
        fraud_ratio=args.fraud_ratio,
        seed=args.seed,
    )
    df = gen.generate()

    fraud_count = df["is_fraud"].sum()
    logger.info(f"Generated {len(df)} transactions ({fraud_count} fraud, {fraud_count/len(df)*100:.1f}%)")

    output_path = Path(args.output)
    gen.save_to_parquet(df, output_path)
    logger.info(f"Saved to {output_path} ({output_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
