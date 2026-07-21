import numpy as np
import pandas as pd


class SyntheticUPIGenerator:
    def __init__(
        self,
        n_users: int = 10_000,
        n_merchants: int = 1_000,
        n_transactions: int = 50_000,
        fraud_ratio: float = 0.05,
    ):
        self.n_users = n_users
        self.n_merchants = n_merchants
        self.n_transactions = n_transactions
        self.fraud_ratio = fraud_ratio

    def generate(self) -> pd.DataFrame:
        pass

    def inject_fraud(self, df: pd.DataFrame) -> pd.DataFrame:
        pass
