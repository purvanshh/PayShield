# ruff: noqa: ARG001, ARG002, ARG005, ASYNC230, ASYNC240 -- test doubles + async file helpers

from datetime import UTC, datetime

import pytest

from observability import metrics as metrics_module
from store.feature_registry import (
    FeatureDefinition,
    FeatureLogEntry,
    FeatureRegistry,
    FeatureSource,
    FeatureType,
    FeatureVersionManager,
)
from store.feature_vector import (
    FeatureVector,
    FeatureVectorBuilder,
    PointInTimeFeatureExtractor,
)
from store.postgres import close_db, get_engine, get_session_maker


class TestFeatureVector:
    def test_to_dict_filters_none_features(self):
        vector = FeatureVector(
            user_id="U1",
            transaction_id="T1",
            features={"amount": 100.5, "spent": None, "category": "grocery"},
            meta={"feature_count": 2},
            version=3,
        )
        data = vector.to_dict()
        assert data["user_id"] == "U1"
        assert data["transaction_id"] == "T1"
        assert data["features"] == {"amount": 100.5, "category": "grocery"}
        assert data["meta"] == {"feature_count": 2}
        assert data["version"] == 3
        assert data["training_timestamp"] is None
        assert data["serving_timestamp"].endswith("+00:00")

    def test_to_csv_row_and_header(self):
        vector = FeatureVector(
            user_id="U1",
            transaction_id="T1",
            features={"amount": 10, "note": None, "flag": True},
            version=2,
        )
        row = vector.to_csv_row()
        assert row[0] == "U1"
        assert row[1] == "T1"
        assert row[4] == "2"
        assert "10" in row
        assert row[-2] == ""  # None -> empty
        assert row[-1] == "True"

        header = FeatureVector.csv_header(["amount", "flag"])
        assert header[:5] == [
            "user_id",
            "transaction_id",
            "training_timestamp",
            "serving_timestamp",
            "version",
        ]
        assert header[5:] == ["amount", "flag"]

    def test_feature_vector_to_arff(self):
        vector = FeatureVector(
            user_id="U1",
            features={"amount": 12.5, "flag": True, "cat": "a"},
        )
        arff = FeatureVectorBuilder.feature_vector_to_arff(vector)
        lines = arff.splitlines()
        assert lines[0] == "@RELATION payshield_features"
        assert "@ATTRIBUTE amount NUMERIC" in lines
        assert "@ATTRIBUTE flag {True,False}" in lines
        assert "@ATTRIBUTE cat STRING" in lines
        assert lines[-1] == "12.5,True,a"


class TestFeatureRegistry:
    @pytest.fixture(autouse=True)
    def _redis(self):
        from tests.fake_redis import FakeRedis

        self.redis = FakeRedis()

    def _amount_def(self):
        return FeatureDefinition(
            name="amount",
            feature_type=FeatureType.NUMERIC,
            source=FeatureSource.TRANSACTION,
            min_val=0,
            max_val=1000,
        )

    def test_register_get_list_and_schema(self):
        reg = FeatureRegistry(self.redis)
        reg.register_definition(self._amount_def())
        assert reg.get_definition("amount").name == "amount"
        assert reg.get_definition("missing") is None
        assert [d.name for d in reg.list_features()] == ["amount"]
        assert [d.name for d in reg.list_features(FeatureSource.TRANSACTION)] == ["amount"]
        assert reg.list_features(FeatureSource.VELOCITY) == []
        schema = reg.get_feature_vector_schema()
        assert schema[0]["feature_type"] == "numeric"
        assert schema[0]["source"] == "transaction"

    def test_validate_value(self):
        reg = FeatureRegistry(self.redis)
        reg.register_definition(self._amount_def())
        assert reg.validate_value("amount", 50) is True
        assert reg.validate_value("amount", 5000) is False
        assert reg.validate_value("amount", "high") is False
        assert reg.validate_value("unknown", 1) is True
        non_nullable = FeatureDefinition(
            name="required", feature_type=FeatureType.NUMERIC, source=FeatureSource.DEVICE,
            nullable=False,
        )
        reg.register_definition(non_nullable)
        assert reg.validate_value("required", None) is False
        cat_def = FeatureDefinition(
            name="cat", feature_type=FeatureType.CATEGORICAL, source=FeatureSource.VELOCITY,
            categories=["a", "b"],
        )
        reg.register_definition(cat_def)
        assert reg.validate_value("cat", "a") is True
        assert reg.validate_value("cat", "zzz") is False

    @pytest.mark.asyncio
    async def test_log_and_get_feature_logs(self):
        reg = FeatureRegistry(self.redis)
        entry = FeatureLogEntry(
            feature_name="amount",
            value=42.0,
            version=1,
            timestamp=1700000000.0,
            transaction_id="T1",
            user_id="U1",
        )
        await reg.log_feature(entry)
        today = datetime.now(UTC).strftime("%Y%m%d")
        logs = await reg.get_feature_logs("amount", today)
        assert len(logs) == 1
        assert logs[0].value == 42.0
        assert logs[0].user_id == "U1"

    @pytest.mark.asyncio
    async def test_compute_psi(self):
        reg = FeatureRegistry(self.redis)
        for i in range(4):
            await reg.log_feature(
                FeatureLogEntry("amt", i, 1, 1700000000.0 + i)
            )
        psi = await reg.compute_psi("amt", {"0": 0.5, "1": 0.5})
        assert psi > 0
        empty = await reg.compute_psi("other", {"0": 1.0})
        assert empty == 0.0

    def test_load_from_config_missing_file(self):
        reg = FeatureRegistry(self.redis, config_path="/nonexistent/registry.yaml")
        assert reg._definitions == {}

    def test_load_from_config_parses_yaml(self, tmp_path):
        config = tmp_path / "registry.yaml"
        config.write_text(
            "features:\n"
            "  - name: amount\n"
            "    type: numeric\n"
            "    source: transaction\n"
            "    min_val: 0\n"
            "    max_val: 10000\n"
        )
        reg = FeatureRegistry(self.redis, config_path=str(config))
        assert "amount" in reg._definitions


@pytest.mark.asyncio
class TestFeatureVectorBuilder:
    @pytest.fixture(autouse=True)
    def _registry(self):
        from tests.fake_redis import FakeRedis

        self.registry = FeatureRegistry(FakeRedis())
        self.registry.register_definition(
            FeatureDefinition(
                name="amount",
                feature_type=FeatureType.NUMERIC,
                source=FeatureSource.TRANSACTION,
                min_val=0,
                max_val=1000,
            )
        )
        self.registry.register_definition(
            FeatureDefinition(
                name="spend_z",
                feature_type=FeatureType.NUMERIC,
                source=FeatureSource.BASELINE,
                min_val=-3,
                max_val=3,
            )
        )

    def _build(self):
        return FeatureVectorBuilder(self.registry)

    async def test_build_merges_and_validates(self):
        vector = await self._build().build(
            user_id="U1",
            transaction_id="T1",
            velocity_features={"txn_count_5m": 3},
            device_features={"device_context": 1},
            transaction_features={"amount": 250, "spend_z": 99},
        )
        assert vector.user_id == "U1"
        assert vector.features["txn_count_5m"] == 3
        assert vector.features["device_context"] == 1
        assert vector.features["amount"] == 250
        assert "spend_z" not in vector.features
        assert vector.meta["feature_count"] == 3
        assert "transaction" in vector.meta["sources"]

    async def test_unknown_features_passthrough(self):
        vector = await self._build().build(
            user_id="U1",
            transaction_features={"mystery": 7},
        )
        assert vector.features["mystery"] == 7

    async def test_extractor_training_and_serving(self):
        from tests.fake_redis import FakeRedis

        extractor = PointInTimeFeatureExtractor(self.registry, FakeRedis())
        at = datetime(2026, 1, 1, tzinfo=UTC)

        async def velocity_fn(user_id):
            return {"txn_count_5m": 2}

        async def baseline_fn(user_id):
            return {"spend_z": 0.5}

        trained = await extractor.extract_training_vector(
            "U9", at, velocity_features_fn=velocity_fn,
            device_features_fn=lambda uid: {"device_context": 1},
            baseline_features_fn=baseline_fn,
        )
        assert trained.training_timestamp == at
        assert trained.features["txn_count_5m"] == 2
        assert trained.features["spend_z"] == 0.5
        assert trained.features["device_context"] == 1

        serving = await extractor.extract_serving_vector(
            "U9", "T9", transaction_features={"amount": 5},
        )
        assert serving.transaction_id == "T9"
        assert serving.features["amount"] == 5


@pytest.mark.asyncio
class TestFeatureVersionManager:
    async def test_get_and_bump(self):
        from tests.fake_redis import FakeRedis

        redis = FakeRedis()
        manager = FeatureVersionManager(redis)
        assert await manager.get_version("amount") == 1
        await manager.bump_version("amount")
        assert await manager.get_version("amount") > 1


class TestStoreModels:
    def test_table_names_registered(self):
        from store.models import Base

        tables = Base.metadata.tables
        for name in (
            "layer1_audit_log",
            "investigation_reports",
            "analyst_feedback",
            "mitigation_actions",
            "graph_transaction_log",
            "users",
            "api_keys",
            "admin_audit_log",
        ):
            assert name in tables

    def test_models_constructible(self):
        from store.models import (
            AdminAuditLog,
            AnalystFeedback,
            ApiKey,
            AuditLog,
            GraphTransactionLog,
            InvestigationReport,
            MitigationAction,
            User,
        )

        AuditLog(txn_id_hash="h", user_id="u", decision="ALLOW")
        InvestigationReport(
            txn_id_hash="h",
            narrative="narrative of sufficient length for the report",
            fraud_type="OTHER",
            confidence="LOW",
            recommended_action="ALLOW",
            key_evidence_json={"items": ["a"]},
            generated_at=datetime.now(),
        )
        AnalystFeedback(
            txn_id_hash="h",
            original_decision="ALLOW",
            analyst_decision="REVIEW",
            analyst_id="a1",
            category="FALSE_POSITIVE",
        )
        MitigationAction(
            txn_id_hash="h",
            action_type="BLOCK",
            target_id="U1",
            reason="fraud",
            executed_by="system",
            executed_at=datetime.now(),
        )
        GraphTransactionLog(
            txn_id_hash="h", user_id="U1", merchant_id="M1", amount=10.0,
        )
        User(username="alice", password_hash="x", role="analyst")
        ApiKey(key_prefix="pk_live", key_hash="hash", name="ci")
        AdminAuditLog(
            admin_id="a1", action="rotate_key", payload_json={"k": 1},
            timestamp=datetime.now(),
        )

    def test_check_constraints_defined(self):
        from store.models import AuditLog, InvestigationReport, User

        assert any(
            c.name == "ck_audit_decision"
            for c in AuditLog.__table__.constraints
            if hasattr(c, "name")
        )
        assert any(
            c.name == "ck_fraud_type"
            for c in InvestigationReport.__table__.constraints
            if hasattr(c, "name")
        )
        assert any(
            c.name == "ck_user_role"
            for c in User.__table__.constraints
            if hasattr(c, "name")
        )


class TestMetrics:
    def test_metric_objects_registered(self):
        assert metrics_module.fraud_score_histogram._name == "fraud_score"
        assert metrics_module.inference_latency._labelnames == ("layer",)
        assert metrics_module.layer1_block_rate._name == "layer1_block"
        assert metrics_module.layer2_escalation_rate._name == "layer2_escalation"
        assert metrics_module.llm_queue_depth._name == "llm_investigation_queue_depth"
        assert metrics_module.redis_hit_rate._name == "redis_feature_store_hit_rate"

    def test_counters_increment(self):
        before = metrics_module.layer1_block_rate._value.get()
        metrics_module.layer1_block_rate.inc(1)
        assert metrics_module.layer1_block_rate._value.get() == before + 1


class TestPostgresGlobals:
    def test_engine_and_session_maker_singletons(self, monkeypatch):
        monkeypatch.setattr(store_postgres_module, "_engine", None)
        monkeypatch.setattr(store_postgres_module, "_session_maker", None)
        engine = get_engine()
        assert engine is get_engine()
        maker = get_session_maker()
        assert maker is get_session_maker()
        assert maker is not None

    @pytest.mark.asyncio
    async def test_close_db_resets_engine(self, monkeypatch):
        class FakeEngine:
            async def dispose(self):
                pass

        monkeypatch.setattr(store_postgres_module, "_engine", FakeEngine())
        await close_db()
        assert store_postgres_module._engine is None


import store.postgres as store_postgres_module  # noqa: E402

for _metric in (
    metrics_module.llm_queue_depth,
    metrics_module.redis_hit_rate,
):
    _metric._value.set(0)
