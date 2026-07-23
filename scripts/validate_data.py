import argparse
import logging
from pathlib import Path

import pandas as pd

from data.validation.validator import DataValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Validate synthetic data quality")
    parser.add_argument("--input", type=str, default="data/raw/synthetic_transactions.parquet", help="Input parquet path")
    parser.add_argument("--transactions-only", action="store_true", help="Only validate transactions")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return

    df = pd.read_parquet(input_path)
    logger.info(f"Loaded {len(df)} rows from {input_path}")

    validator = DataValidator()
    report = validator.validate_transactions(df)

    print(f"\n{'─' * 50}")
    print(report.summary())
    print(f"{'─' * 50}")

    if report.is_valid:
        logger.info("All validation checks passed")
    else:
        logger.warning(f"{report.failed_expectations} expectation(s) failed")

    if not args.transactions_only:
        users_path = input_path.parent / "synthetic_users.parquet"
        merchants_path = input_path.parent / "synthetic_merchants.parquet"

        if users_path.exists():
            users_df = pd.read_parquet(users_path)
            user_report = validator.validate_users(users_df)
            print(f"\nUsers: {user_report.summary()}")

        if merchants_path.exists():
            merchants_df = pd.read_parquet(merchants_path)
            merchant_report = validator.validate_merchants(merchants_df)
            print(f"\nMerchants: {merchant_report.summary()}")


if __name__ == "__main__":
    main()
