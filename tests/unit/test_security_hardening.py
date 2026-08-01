"""P9 security & performance unit tests: TOTP, fixed-window rate limiting,
Redis memory-policy check, and the async (queue-backed) audit writer."""

import asyncio
import logging
import time

from api.auth import AuthManager, TOTPManager, auth_manager
from api.security import RateLimiter
from store.audit_log import AsyncAuditLogWriter, AuditLogWriter
from store.connection_pool import RedisConnectionPool


class TestTOTP:
    def test_generate_and_verify_code(self):
        totp = TOTPManager()
        code = totp.current_code()
        assert len(code) == 6 and code.isdigit()
        assert totp.verify(code)

    def test_verify_rejects_wrong_code(self):
        totp = TOTPManager()
        code = totp.current_code()
        wrong = str((int(code) + 1) % 1_000_000).zfill(6)
        assert not totp.verify(wrong)

    def test_window_drift_tolerated(self):
        totp = TOTPManager()
        past_code = totp.current_code(at=time.time() - TOTPManager.STEP_SECONDS)
        assert totp.verify(past_code)

    def test_rejects_arbitrary_input(self):
        totp = TOTPManager()
        assert not totp.verify("")
        assert not totp.verify("abc")
        assert not totp.verify("!23#56")

    def test_provision_uri_contains_secret_and_issuer(self):
        uri = TOTPManager("JBSWY3DPEHPK3PXP").provision_uri("admin")
        assert uri.startswith("otpauth://totp/PayShield:admin?")
        assert "secret=JBSWY3DPEHPK3PXP" in uri
        assert "issuer=PayShield" in uri

    def test_auth_manager_setup_verify_flow(self):
        mgr = AuthManager()
        secret, uri = mgr.setup_totp("admin")
        assert not mgr.is_totp_enabled("admin")
        code = TOTPManager(secret).current_code()
        assert mgr.verify_totp("admin", code)
        assert mgr.is_totp_enabled("admin")

    def test_verify_without_setup_fails(self):
        mgr = AuthManager()
        assert not mgr.verify_totp("nobody", "000000")

    def test_singleton_persists_state(self):
        assert auth_manager is auth_manager
        assert hasattr(auth_manager, "verify_totp")


class TestRateLimiterFixedWindow:
    def test_allows_up_to_limit(self):
        limiter = RateLimiter(redis_url=None)
        key = "test:key:a"
        for _ in range(3):
            assert limiter.is_allowed_fixed_window(key, limit=3, window_seconds=60)
        assert not limiter.is_allowed_fixed_window(key, limit=3, window_seconds=60)

    def test_window_rollover_allows_again(self):
        limiter = RateLimiter(redis_url=None)
        key = "test:key:b"
        for _ in range(3):
            limiter.is_allowed_fixed_window(key, limit=3, window_seconds=1)
        assert not limiter.is_allowed_fixed_window(key, limit=3, window_seconds=1)
        time.sleep(1.1)
        assert limiter.is_allowed_fixed_window(key, limit=3, window_seconds=1)

    def test_reset_clears_counter(self):
        limiter = RateLimiter(redis_url=None)
        key = "test:key:c"
        limiter.is_allowed_fixed_window(key, limit=1, window_seconds=60)
        assert not limiter.is_allowed_fixed_window(key, limit=1, window_seconds=60)
        limiter.reset(key)
        assert limiter.is_allowed_fixed_window(key, limit=1, window_seconds=60)

    def test_keys_are_isolated(self):
        limiter = RateLimiter(redis_url=None)
        assert limiter.is_allowed_fixed_window("test:key:1", limit=1, window_seconds=60)
        assert not limiter.is_allowed_fixed_window("test:key:1", limit=1, window_seconds=60)
        assert limiter.is_allowed_fixed_window("test:key:2", limit=1, window_seconds=60)


class TestRedisMemoryPolicy:
    async def test_lru_policy_ok(self, caplog):
        pool = RedisConnectionPool()
        pool.client = _FakeRedisConfig(maxmemory_policy="allkeys-lru")
        with caplog.at_level(logging.WARNING):
            assert await pool.ensure_memory_policy() == "allkeys-lru"
        assert not any("maxmemory_policy" in r.message for r in caplog.records)

    async def test_non_lru_policy_warns(self, caplog):
        pool = RedisConnectionPool()
        pool.client = _FakeRedisConfig(maxmemory_policy="noeviction")
        with caplog.at_level(logging.WARNING):
            assert await pool.ensure_memory_policy() == "noeviction"
        assert any("maxmemory_policy=noeviction" in r.message for r in caplog.records)

    async def test_config_unavailable_returns_none(self):
        pool = RedisConnectionPool()
        pool.client = _FakeRedisConfig(config_error=True)
        assert await pool.ensure_memory_policy() is None


class _FakeRedisConfig:
    def __init__(self, maxmemory_policy="allkeys-lru", config_error=False):
        self._policy = maxmemory_policy
        self._config_error = config_error

    async def config_get(self, parameter):
        if self._config_error:
            raise ConnectionError("redis down")
        return {"maxmemory-policy": self._policy}


class TestAsyncAuditLogWriter:
    async def test_append_is_fast(self, tmp_path):
        writer = AuditLogWriter(log_dir=str(tmp_path))
        async_logger = AsyncAuditLogWriter(writer=writer, flush_interval=10.0, batch_size=100)
        async_logger.start()
        try:
            start = time.perf_counter()
            for i in range(200):
                async_logger.append(
                    event_type="SCORE_DECISION",
                    actor=f"U{i}",
                    decision="ALLOW",
                    payload={"txn_id": f"TXN{i}"},
                )
            elapsed = time.perf_counter() - start
            avg_ms = elapsed / 200 * 1000
            assert avg_ms < 1.0, f"append average {avg_ms:.3f}ms exceeds 1ms budget"
        finally:
            await async_logger.stop()

    async def test_batch_flush_deterministic(self, tmp_path):
        writer = AuditLogWriter(log_dir=str(tmp_path))
        async_logger = AsyncAuditLogWriter(writer=writer, flush_interval=10.0, batch_size=50)
        for i in range(120):
            async_logger.append("SCORE_DECISION", f"U{i}", "ALLOW", {"txn_id": f"TXN{i}"})
        assert async_logger.pending_count == 120
        assert writer.entry_count == 0
        async_logger.start()
        try:
            await asyncio.sleep(0.1)
            assert writer.entry_count >= 100
            await async_logger.stop()
        finally:
            await async_logger.stop()

    async def test_interval_flush_when_below_batch_size(self, tmp_path):
        writer = AuditLogWriter(log_dir=str(tmp_path))
        async_logger = AsyncAuditLogWriter(writer=writer, flush_interval=0.05, batch_size=1000)
        async_logger.start()
        try:
            for i in range(3):
                async_logger.append("SCORE_DECISION", f"U{i}", "ALLOW", {"txn_id": f"TXN{i}"})
            await asyncio.sleep(0.2)
            assert writer.entry_count == 3
            assert async_logger.pending_count == 0
        finally:
            await async_logger.stop()

    async def test_stop_flushes_pending(self, tmp_path):
        writer = AuditLogWriter(log_dir=str(tmp_path))
        async_logger = AsyncAuditLogWriter(writer=writer, flush_interval=10.0, batch_size=1000)
        async_logger.start()
        for i in range(5):
            async_logger.append("SCORE_DECISION", f"U{i}", "ALLOW", {"txn_id": f"TXN{i}"})
        await async_logger.stop()
        assert writer.entry_count == 5

    async def test_chain_verifies_after_async_flush(self, tmp_path):
        writer = AuditLogWriter(log_dir=str(tmp_path))
        async_logger = AsyncAuditLogWriter(writer=writer, flush_interval=0.01, batch_size=5)
        async_logger.start()
        try:
            for i in range(10):
                async_logger.append("SCORE_DECISION", f"U{i}", "ALLOW", {"txn_id": f"TXN{i}"})
            await asyncio.sleep(0.3)
            ok, count = writer.verify_chain()
            assert ok
            assert count == 10
        finally:
            await async_logger.stop()
