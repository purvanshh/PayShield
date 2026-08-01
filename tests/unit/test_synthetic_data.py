
from data.synthetic_upi import SyntheticUPIGenerator


class TestSyntheticUPIGenerator:
    def test_generates_correct_number_of_transactions(self):
        gen = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=1000, fraud_ratio=0.05)
        df = gen.generate()
        assert len(df) == 1000

    def test_injects_fraud(self):
        gen = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=1000, fraud_ratio=0.05)
        df = gen.generate()
        fraud_count = df["is_fraud"].sum()
        assert fraud_count > 0
        assert fraud_count <= 100

    def test_fraud_types_present(self):
        gen = SyntheticUPIGenerator(n_users=200, n_merchants=100, n_transactions=2000, fraud_ratio=0.05)
        df = gen.generate()
        fraud_types = df[df["is_fraud"]]["fraud_type"].unique()
        assert "MULE_RING" in fraud_types
        assert "BURST_ATTACK" in fraud_types
        assert "MERCHANT_COLLUSION" in fraud_types
        assert "ATO" in fraud_types

    def test_required_columns(self):
        gen = SyntheticUPIGenerator(n_users=50, n_merchants=20, n_transactions=500)
        df = gen.generate()
        required = ["txn_id", "user_id", "merchant_id", "amount", "timestamp",
                     "device_fingerprint", "lat", "lon", "mcc_code", "txn_type",
                     "is_fraud", "fraud_type"]
        for col in required:
            assert col in df.columns

    def test_amounts_positive(self):
        gen = SyntheticUPIGenerator(n_users=50, n_merchants=20, n_transactions=500)
        df = gen.generate()
        assert (df["amount"] > 0).all()

    def test_txn_types_valid(self):
        gen = SyntheticUPIGenerator(n_users=50, n_merchants=20, n_transactions=500)
        df = gen.generate()
        valid_types = {"P2P", "P2M", "COLLECT"}
        assert df["txn_type"].isin(valid_types).all()

    def test_deterministic_seed(self):
        gen1 = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=1000, seed=42)
        gen2 = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=1000, seed=42)
        df1 = gen1.generate()
        df2 = gen2.generate()
        assert df1["txn_id"].equals(df2["txn_id"])

    def test_different_seeds_differ(self):
        gen1 = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=1000, seed=42)
        gen2 = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=1000, seed=99)
        df1 = gen1.generate()
        df2 = gen2.generate()
        assert not df1["amount"].equals(df2["amount"])
