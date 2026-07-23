from dataclasses import dataclass, field


@dataclass
class ExpectationResult:
    passed: bool
    name: str
    total: int = 0
    failed: int = 0
    details: list[str] = field(default_factory=list)


def expect_unique(series, column: str) -> ExpectationResult:
    total = len(series)
    duplicates = series.duplicated()
    n_failed = int(duplicates.sum())
    failed_vals = series[duplicates].unique().tolist()
    return ExpectationResult(
        passed=n_failed == 0,
        name=f"{column}_unique",
        total=total,
        failed=n_failed,
        details=[f"{column}: {n_failed} duplicates: {failed_vals[:5]}"] if n_failed > 0 else [],
    )


def expect_positive(series, column: str) -> ExpectationResult:
    total = len(series)
    below = series <= 0
    n_failed = int(below.sum())
    return ExpectationResult(
        passed=n_failed == 0,
        name=f"{column}_positive",
        total=total,
        failed=n_failed,
        details=[f"{column}: {n_failed} non-positive values"] if n_failed > 0 else [],
    )


def expect_in_range(series, column: str, lo: float, hi: float) -> ExpectationResult:
    total = len(series)
    out_of_range = (series < lo) | (series > hi)
    n_failed = int(out_of_range.sum())
    return ExpectationResult(
        passed=n_failed == 0,
        name=f"{column}_in_range[{lo},{hi}]",
        total=total,
        failed=n_failed,
        details=[f"{column}: {n_failed} out of range [{lo}, {hi}]"] if n_failed > 0 else [],
    )


def expect_not_null(series, column: str) -> ExpectationResult:
    total = len(series)
    nulls = series.isna()
    n_failed = int(nulls.sum())
    return ExpectationResult(
        passed=n_failed == 0,
        name=f"{column}_not_null",
        total=total,
        failed=n_failed,
        details=[f"{column}: {n_failed} null values"] if n_failed > 0 else [],
    )


def expect_in_set(series, column: str, allowed: set) -> ExpectationResult:
    total = len(series)
    invalid = ~series.isin(allowed)
    n_failed = int(invalid.sum())
    failed_vals = series[invalid].unique().tolist()
    return ExpectationResult(
        passed=n_failed == 0,
        name=f"{column}_in_set",
        total=total,
        failed=n_failed,
        details=[f"{column}: {n_failed} invalid values: {failed_vals[:5]}"] if n_failed > 0 else [],
    )


def expect_reference_exists(series, column: str, reference: set) -> ExpectationResult:
    total = len(series)
    missing = ~series.isin(reference)
    n_failed = int(missing.sum())
    return ExpectationResult(
        passed=n_failed == 0,
        name=f"{column}_references_exist",
        total=total,
        failed=n_failed,
        details=[f"{column}: {n_failed} missing references"] if n_failed > 0 else [],
    )


def expect_fraud_pattern_not_null(df) -> ExpectationResult:
    fraud_rows = df[df["is_fraud"]]
    total = len(fraud_rows)
    null_patterns = fraud_rows["fraud_pattern"].isna()
    n_failed = int(null_patterns.sum())
    return ExpectationResult(
        passed=n_failed == 0,
        name="fraud_pattern_not_null_when_fraud",
        total=total,
        failed=n_failed,
        details=[f"{n_failed} fraud rows without fraud_pattern"] if n_failed > 0 else [],
    )
