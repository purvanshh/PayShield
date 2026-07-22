from datetime import datetime

import pytest
from pydantic import ValidationError

from api.schemas import (
    TransactionEvent, FraudScoreResponse, BatchScoreRequest,
    InvestigationReport, FeedbackRequest, GeoPoint,
)


class TestGeoPoint:
    def test_valid_geopoint(self):
        g = GeoPoint(lat=19.076, lon=72.877)
        assert g.lat == 19.076
        assert g.lon == 72.877


class TestTransactionEvent:
    def test_valid_transaction(self):
        txn = TransactionEvent(
            txn_id="TXN0001",
            user_id="U000001",
            merchant_id="M00001",
            amount=500.0,
            timestamp=datetime.utcnow(),
            device_fingerprint="D1",
            location=GeoPoint(lat=19.0, lon=72.0),
            mcc_code="food",
            txn_type="P2M",
        )
        assert txn.txn_id == "TXN0001"

    def test_invalid_txn_type(self):
        with pytest.raises(ValidationError):
            TransactionEvent(
                txn_id="TXN0001",
                user_id="U000001",
                merchant_id="M00001",
                amount=500.0,
                timestamp=datetime.utcnow(),
                device_fingerprint="D1",
                location=GeoPoint(lat=19.0, lon=72.0),
                mcc_code="food",
                txn_type="INVALID",
            )

    def test_negative_amount(self):
        with pytest.raises(ValidationError):
            TransactionEvent(
                txn_id="TXN0001",
                user_id="U000001",
                merchant_id="M00001",
                amount=-100.0,
                timestamp=datetime.utcnow(),
                device_fingerprint="D1",
                location=GeoPoint(lat=19.0, lon=72.0),
                mcc_code="food",
                txn_type="P2P",
            )


class TestFraudScoreResponse:
    def test_valid_response(self):
        resp = FraudScoreResponse(
            txn_id="TXN0001",
            decision="BLOCK",
            fraud_probability=0.95,
            layer_triggered="L2_GNN",
            evidence={"rule": "velocity"},
            latency_ms=12.5,
            model_version="1.0.0",
        )
        assert resp.decision == "BLOCK"

    def test_invalid_decision(self):
        with pytest.raises(ValidationError):
            FraudScoreResponse(
                txn_id="TXN0001",
                decision="INVALID",
                fraud_probability=0.5,
                layer_triggered="L1_STATISTICAL",
                evidence={},
                latency_ms=0,
                model_version="1.0.0",
            )


class TestBatchScoreRequest:
    def test_valid_batch(self):
        batch = BatchScoreRequest(transactions=[])
        assert len(batch.transactions) == 0

    def test_batch_with_transactions(self):
        txn = TransactionEvent(
            txn_id="TXN0001",
            user_id="U1",
            merchant_id="M1",
            amount=100.0,
            timestamp=datetime.utcnow(),
            device_fingerprint="D1",
            location=GeoPoint(lat=19.0, lon=72.0),
            mcc_code="food",
            txn_type="P2M",
        )
        batch = BatchScoreRequest(transactions=[txn])
        assert len(batch.transactions) == 1


class TestInvestigationReport:
    def test_valid_report(self):
        report = InvestigationReport(
            txn_id="TXN0001",
            narrative="Suspicious activity detected",
            fraud_type="MULE_RING",
            confidence=0.92,
            recommended_action="Block account",
            generated_at=datetime.utcnow(),
        )
        assert report.fraud_type == "MULE_RING"


class TestFeedbackRequest:
    def test_valid_feedback(self):
        fb = FeedbackRequest(
            txn_id="TXN0001",
            analyst_id="analyst_1",
            correct_decision="BLOCK",
            comment="Confirmed mule account",
        )
        assert fb.analyst_id == "analyst_1"
