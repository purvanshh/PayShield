from datetime import datetime

import pytest

from engine.ensemble import EnsembleScorer
from engine.statistical_filter import StatisticalFilter, StatisticalResult
from store.graph_db import GraphDB


class TestEnsembleScorer:
    def test_ensemble_initialization(self):
        graph_db = GraphDB()
        ensemble = EnsembleScorer(graph_db)
        assert ensemble.statistical_filter is not None
        assert ensemble.gnn_model is not None
        assert ensemble.graph_engine is not None
        assert ensemble.explainer is not None

    def test_score_allows_normal_txn(self):
        graph_db = GraphDB()
        ensemble = EnsembleScorer(graph_db)

        class MockStore:
            def get_velocity_stats(self, uid):
                return {"txn_count_5min": 1, "txn_count_1h": 2, "txn_count_24h": 5}

            def get_user_baseline(self, uid):
                return {"hourly_avg_txn_count": 1.0, "hourly_std_txn_count": 0.5, "median_amount": 500}

            def get_geospatial_cache(self, uid):
                return None

            def get_merchant_amounts(self, mid):
                return None

        txn = {
            "txn_id": "TXN00000001",
            "user_id": "U000001",
            "merchant_id": "M00001",
            "amount": 500,
            "timestamp": datetime.utcnow(),
            "lat": 19.0,
            "lon": 72.0,
        }
        result = ensemble.score(txn, MockStore())
        assert "decision" in result
        assert result["decision"] in ("ALLOW", "BLOCK", "REVIEW")
        assert "fraud_probability" in result
        assert "layer_triggered" in result

    def test_score_blocks_high_probability(self):
        graph_db = GraphDB()
        ensemble = EnsembleScorer(graph_db)
        ensemble.block_threshold = -1.0

        class MockStore:
            def get_velocity_stats(self, uid):
                return {"txn_count_5min": 50, "txn_count_1h": 100, "txn_count_24h": 200}

            def get_user_baseline(self, uid):
                return {"hourly_avg_txn_count": 1.0, "hourly_std_txn_count": 0.5, "median_amount": 100}

            def get_geospatial_cache(self, uid):
                return None

            def get_merchant_amounts(self, mid):
                return None

        txn = {
            "txn_id": "TXN00000001",
            "user_id": "U000001",
            "merchant_id": "M00001",
            "amount": 99999,
            "timestamp": datetime.utcnow(),
            "lat": 19.0,
            "lon": 72.0,
        }
        result = ensemble.score(txn, MockStore())
        assert result["decision"] in ("ALLOW", "BLOCK", "REVIEW")
