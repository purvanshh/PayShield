from engine.statistical_filter import StatisticalFilter, StatisticalResult
from engine.graph_model import PayShieldGNN


class EnsembleScorer:
    def __init__(self):
        self.statistical_filter = StatisticalFilter()
        self.gnn_model = PayShieldGNN()

    def score(self, txn, feature_store):
        pass
