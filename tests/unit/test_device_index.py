# ruff: noqa: ARG002 -- stub redis mirrors the client interface

import pytest

from store.device_index import (
    DeviceFeatureExtractor,
    DeviceFingerprint,
    DeviceFingerprintIndex,
)


@pytest.fixture()
def redis():
    from tests.fake_redis import FakeRedis

    return FakeRedis()


def _fp(ip="1.2.3.4", ua="Mozilla/5.0", **kwargs):
    defaults = {
        "device_id": "D1",
        "ip_address": ip,
        "user_agent": ua,
        "screen_resolution": "1920x1080",
        "timezone": "Asia/Kolkata",
        "language": "en-IN",
        "installed_fonts": ["Arial", "Helvetica"],
        "installed_plugins": ["pdf"],
    }
    defaults.update(kwargs)
    return DeviceFingerprint(**defaults)


class TestDeviceFingerprint:
    def test_to_features_and_fingerprint_hash(self):
        fp = _fp()
        features = fp.to_features()
        assert "ip:1.2.3.4" in features
        assert any(f.startswith("ua:") for f in features)
        assert any(f.startswith("font:") for f in features)
        assert "screen:1920x1080" in features
        assert "tz:Asia/Kolkata" in features
        assert "lang:en-IN" in features
        assert fp.fingerprint_hash() == fp.fingerprint_hash()
        assert len(fp.fingerprint_hash()) == 16

    def test_to_features_truncates_lists(self):
        fp = _fp(installed_fonts=[f"font{i}" for i in range(20)])
        font_features = [f for f in fp.to_features() if f.startswith("font:")]
        assert len(font_features) == 10


@pytest.mark.asyncio
class TestDeviceFingerprintIndex:
    async def test_register_and_lookup(self, redis):
        index = DeviceFingerprintIndex(redis)
        is_new = await index.register("D1", "U1", _fp())
        assert is_new is True
        assert await index.register("D1", "U1", _fp()) is False

        fp = await index.lookup("D1")
        assert fp is not None
        assert fp.user_id == "U1"
        assert fp.ip_address == "1.2.3.4"
        assert fp.canvas_hash is None
        assert fp.screen_resolution == "1920x1080"
        assert fp.first_seen is not None

        assert await index.lookup("D9") is None

    async def test_devices_for_user_and_multi_device(self, redis):
        index = DeviceFingerprintIndex(redis)
        await index.register("D1", "U1", _fp())
        await index.register("D2", "U1", _fp(ip="5.6.7.8", ua="Mozilla/5.0"))
        devices = await index.get_devices_for_user("U1")
        assert set(devices) == {"D1", "D2"}
        assert await index.detect_multi_device("U1") == 2

    async def test_jaccard_similarity(self, redis):
        index = DeviceFingerprintIndex(redis)
        await index.register("D1", "U1", _fp())
        await index.register("D2", "U2", _fp())
        assert await index.compute_jaccard("D1", "D2") == pytest.approx(1.0, abs=0.01)
        assert await index.compute_jaccard("D1", "D9") == 0.0

    async def test_is_emulator(self, redis):
        index = DeviceFingerprintIndex(redis)
        await index.register("D1", "U1", _fp(ua="Mozilla/5.0 (Linux; Android 13; Android SDK built for x86)"))
        assert await index.is_emulator("D1") is True
        await index.register("D2", "U1", _fp(ip="9.9.9.9"))
        assert await index.is_emulator("D2") is False
        assert await index.is_emulator("D9") is False

    async def test_get_device_features(self, redis):
        index = DeviceFingerprintIndex(redis)
        await index.register("D1", "U1", _fp())
        await index.register("D2", "U1", _fp(ip="5.6.7.8"))
        features = await index.get_device_features("D1", "U1")
        assert features.multi_device_count == 2
        assert features.jaccard_similarity == pytest.approx(7/9, abs=0.01)
        assert features.new_device_flag is False
        assert features.txn_count_last_24h == 1
        assert features.proxy_score > 0
        assert features.vpn_detected is False

    async def test_proxy_score_and_vpn(self, redis):
        index = DeviceFingerprintIndex(redis)
        await index.register("D1", "U1", _fp(ip="10.0.0.1"))
        await index.register("D2", "U1", _fp(ip="datacenter-proxy.cloud", ua="x"))
        proxy = await index.get_device_features("D2", "U1")
        assert proxy.proxy_score >= 0.5
        assert proxy.vpn_detected is True

    async def test_extractor_dict(self, redis):
        index = DeviceFingerprintIndex(redis)
        await index.register("D1", "U1", _fp())
        result = await DeviceFeatureExtractor(index).extract("D1", "U1")
        assert result["device_is_emulator"] == 0
        assert result["device_new_flag"] == 0
        assert result["device_multi_device_count"] == 1
        assert result["device_txn_count_24h"] == 1
        assert result["device_proxy_score"] > 0
