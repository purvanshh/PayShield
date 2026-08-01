import pandas as pd

from data.validation.expectations import (
    expect_fraud_pattern_not_null,
    expect_in_range,
    expect_in_set,
    expect_not_null,
    expect_positive,
    expect_reference_exists,
    expect_unique,
)
from data.validation.validator import DataValidator


class TestExpectations:
    def test_expect_unique_passes(self):
        s = pd.Series([1, 2, 3, 4])
        r = expect_unique(s, "test")
        assert r.passed
        assert r.failed == 0

    def test_expect_unique_fails(self):
        s = pd.Series([1, 2, 2, 3])
        r = expect_unique(s, "test")
        assert not r.passed
        assert r.failed == 1

    def test_expect_positive_passes(self):
        s = pd.Series([1.0, 2.5, 100.0])
        r = expect_positive(s, "test")
        assert r.passed

    def test_expect_positive_fails(self):
        s = pd.Series([0.0, -1.0, 5.0])
        r = expect_positive(s, "test")
        assert not r.passed
        assert r.failed == 2

    def test_expect_in_range_passes(self):
        s = pd.Series([300, 500, 900])
        r = expect_in_range(s, "test", 300, 900)
        assert r.passed

    def test_expect_in_range_fails(self):
        s = pd.Series([100, 500, 950])
        r = expect_in_range(s, "test", 300, 900)
        assert not r.passed
        assert r.failed == 2

    def test_expect_not_null(self):
        s = pd.Series([1.0, None, 3.0])
        r = expect_not_null(s, "test")
        assert not r.passed
        assert r.failed == 1

    def test_expect_in_set(self):
        s = pd.Series(["a", "b", "c"])
        r = expect_in_set(s, "test", {"a", "b"})
        assert not r.passed
        assert r.failed == 1

    def test_expect_reference_exists(self):
        s = pd.Series(["U1", "U2", "U3"])
        r = expect_reference_exists(s, "test", {"U1", "U2"})
        assert not r.passed
        assert r.failed == 1

    def test_expect_fraud_pattern_not_null_passes(self):
        df = pd.DataFrame({"is_fraud": [True, False], "fraud_pattern": ["MULE_RING", None]})
        r = expect_fraud_pattern_not_null(df)
        assert r.passed

    def test_expect_fraud_pattern_not_null_fails(self):
        df = pd.DataFrame({"is_fraud": [True, False], "fraud_pattern": [None, None]})
        r = expect_fraud_pattern_not_null(df)
        assert not r.passed
        assert r.failed == 1


class TestDataValidator:
    def test_validates_clean_transactions(self):
        df = pd.DataFrame({
            "txn_id": ["T1", "T2"],
            "user_id": ["U1", "U2"],
            "merchant_id": ["M1", "M2"],
            "amount": [100.0, 200.0],
            "timestamp": pd.to_datetime(["2026-06-01", "2026-06-02"]),
            "mcc_code": ["food", "travel"],
            "txn_type": ["P2M", "P2P"],
            "status": ["SUCCESS", "SUCCESS"],
            "is_fraud": [False, False],
            "fraud_pattern": [None, None],
            "device_fingerprint": ["D1", "D2"],
            "lat": [19.0, 28.0],
            "lon": [72.0, 77.0],
        })
        validator = DataValidator()
        report = validator.validate_transactions(df)
        assert report.is_valid

    def test_fails_on_duplicate_txn_ids(self):
        df = pd.DataFrame({
            "txn_id": ["T1", "T1"],
            "user_id": ["U1", "U2"],
            "merchant_id": ["M1", "M2"],
            "amount": [100.0, 200.0],
            "timestamp": pd.to_datetime(["2026-06-01", "2026-06-02"]),
            "mcc_code": ["food", "travel"],
            "txn_type": ["P2M", "P2P"],
            "status": ["SUCCESS", "SUCCESS"],
            "is_fraud": [False, False],
            "fraud_pattern": [None, None],
            "device_fingerprint": ["D1", "D2"],
            "lat": [19.0, 28.0],
            "lon": [72.0, 77.0],
        })
        validator = DataValidator()
        report = validator.validate_transactions(df)
        assert not report.is_valid

    def test_fails_on_negative_amount(self):
        df = pd.DataFrame({
            "txn_id": ["T1"],
            "user_id": ["U1"],
            "merchant_id": ["M1"],
            "amount": [-100.0],
            "timestamp": pd.to_datetime(["2026-06-01"]),
            "mcc_code": ["food"],
            "txn_type": ["P2M"],
            "status": ["SUCCESS"],
            "is_fraud": [False],
            "fraud_pattern": [None],
            "device_fingerprint": ["D1"],
            "lat": [19.0],
            "lon": [72.0],
        })
        validator = DataValidator()
        report = validator.validate_transactions(df)
        assert not report.is_valid

    def test_validates_users(self):
        df = pd.DataFrame({
            "user_id": ["U1", "U2"],
            "credit_score": [700, 800],
            "account_age_days": [365, 100],
            "age": [32, 45],
            "kyc_tier": [2, 3],
        })
        validator = DataValidator()
        report = validator.validate_users(df)
        assert report.is_valid

    def test_validates_merchants(self):
        df = pd.DataFrame({
            "merchant_id": ["M1", "M2"],
            "avg_txn_amount": [500.0, 1000.0],
            "refund_rate": [0.02, 0.05],
            "mcc_code": ["food", "travel"],
            "account_age_days": [365, 100],
        })
        validator = DataValidator()
        report = validator.validate_merchants(df)
        assert report.is_valid
