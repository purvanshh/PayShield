from dataclasses import dataclass, field

import pandas as pd

from data.validation.expectations import (
    ExpectationResult,
    expect_unique,
    expect_positive,
    expect_in_range,
    expect_not_null,
    expect_in_set,
    expect_reference_exists,
    expect_fraud_pattern_not_null,
)

MCC_CATEGORIES = {
    "food", "travel", "utilities", "fashion", "groceries",
    "entertainment", "health", "education", "transport", "rent",
    "recharge", "insurance", "investment", "cashback", "other",
}

TXN_TYPES = {"P2P", "P2M", "COLLECT"}
STATUSES = {"SUCCESS", "FAILED", "PENDING"}
FRAUD_PATTERNS = {"MULE_RING", "BURST_ATTACK", "MERCHANT_COLLUSION", "ATO"}


@dataclass
class ValidationReport:
    is_valid: bool = True
    total_records: int = 0
    failed_records: int = 0
    passed_expectations: int = 0
    failed_expectations: int = 0
    results: list[ExpectationResult] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Validation Report",
            f"  Total records:    {self.total_records}",
            f"  Failed records:   {self.failed_records}",
            f"  Passed checks:    {self.passed_expectations}",
            f"  Failed checks:    {self.failed_expectations}",
            f"  Overall:          {'PASS' if self.is_valid else 'FAIL'}",
        ]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"    [{status}] {r.name} ({r.failed}/{r.total} failed)")
            for d in r.details:
                lines.append(f"           {d}")
        return "\n".join(lines)


class DataValidator:
    def validate_transactions(self, df: pd.DataFrame, user_ids: set | None = None, merchant_ids: set | None = None) -> ValidationReport:
        results = []
        results.append(expect_unique(df["txn_id"], "txn_id"))
        results.append(expect_positive(df["amount"], "amount"))
        results.append(expect_not_null(df["timestamp"], "timestamp"))
        results.append(expect_not_null(df["user_id"], "user_id"))
        results.append(expect_not_null(df["merchant_id"], "merchant_id"))
        results.append(expect_in_set(df["mcc_code"], "mcc_code", MCC_CATEGORIES))
        results.append(expect_in_set(df["txn_type"], "txn_type", TXN_TYPES))
        results.append(expect_in_set(df["status"], "status", STATUSES))

        if "is_fraud" in df.columns:
            results.append(expect_in_set(df["is_fraud"], "is_fraud", {True, False}))
            results.append(expect_fraud_pattern_not_null(df))
            fraud_df = df[df["is_fraud"]]
            if len(fraud_df) > 0:
                results.append(expect_in_set(fraud_df["fraud_pattern"], "fraud_pattern", FRAUD_PATTERNS))

        if user_ids is not None:
            results.append(expect_reference_exists(df["user_id"], "user_id", user_ids))
        if merchant_ids is not None:
            results.append(expect_reference_exists(df["merchant_id"], "merchant_id", merchant_ids))

        return self._build_report(results, len(df))

    def validate_users(self, df: pd.DataFrame) -> ValidationReport:
        results = []
        results.append(expect_unique(df["user_id"], "user_id"))
        results.append(expect_in_range(df["credit_score"], "credit_score", 300, 900))
        results.append(expect_in_range(df["account_age_days"], "account_age_days", 0, 5000))
        results.append(expect_in_range(df["age"], "age", 18, 100))
        results.append(expect_not_null(df["kyc_tier"], "kyc_tier"))
        return self._build_report(results, len(df))

    def validate_merchants(self, df: pd.DataFrame) -> ValidationReport:
        results = []
        results.append(expect_unique(df["merchant_id"], "merchant_id"))
        results.append(expect_positive(df["avg_txn_amount"], "avg_txn_amount"))
        results.append(expect_in_range(df["refund_rate"], "refund_rate", 0.0, 1.0))
        results.append(expect_in_set(df["mcc_code"], "mcc_code", MCC_CATEGORIES))
        results.append(expect_not_null(df["account_age_days"], "account_age_days"))
        return self._build_report(results, len(df))

    def _build_report(self, results: list[ExpectationResult], total_records: int) -> ValidationReport:
        failed = sum(r.failed for r in results)
        passed_ex = sum(1 for r in results if r.passed)
        failed_ex = sum(1 for r in results if not r.passed)
        return ValidationReport(
            is_valid=failed_ex == 0,
            total_records=total_records,
            failed_records=failed,
            passed_expectations=passed_ex,
            failed_expectations=failed_ex,
            results=results,
        )
