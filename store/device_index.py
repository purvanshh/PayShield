import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class DeviceFingerprint:
    device_id: str
    user_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    screen_resolution: str | None = None
    timezone: str | None = None
    language: str | None = None
    installed_fonts: list[str] = field(default_factory=list)
    installed_plugins: list[str] = field(default_factory=list)
    canvas_hash: str | None = None
    webgl_hash: str | None = None
    audio_hash: str | None = None
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_features(self) -> list[str]:
        features = []
        if self.ip_address:
            features.append(f"ip:{self.ip_address}")
        if self.user_agent:
            ua_hash = hashlib.md5(self.user_agent.encode()).hexdigest()
            features.append(f"ua:{ua_hash}")
        if self.screen_resolution:
            features.append(f"screen:{self.screen_resolution}")
        if self.timezone:
            features.append(f"tz:{self.timezone}")
        if self.language:
            features.append(f"lang:{self.language}")
        if self.canvas_hash:
            features.append(f"canvas:{self.canvas_hash}")
        if self.webgl_hash:
            features.append(f"webgl:{self.webgl_hash}")
        if self.audio_hash:
            features.append(f"audio:{self.audio_hash}")
        for font in self.installed_fonts[:10]:
            features.append(f"font:{hashlib.md5(font.encode()).hexdigest()}")
        for plugin in self.installed_plugins[:10]:
            features.append(f"plugin:{hashlib.md5(plugin.encode()).hexdigest()}")
        return features

    def fingerprint_hash(self) -> str:
        canonical = {
            "ip": self.ip_address,
            "ua": self.user_agent,
            "screen": self.screen_resolution,
            "tz": self.timezone,
            "canvas": self.canvas_hash,
            "webgl": self.webgl_hash,
        }
        raw = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class DeviceFeatures:
    device_id: str
    user_id: str
    is_emulator: bool = False
    is_rooted: bool = False
    is_spoofed: bool = False
    multi_device_count: int = 1
    jaccard_similarity: float = 1.0
    txn_count_last_24h: int = 0
    distinct_users_last_24h: int = 1
    new_device_flag: bool = True
    proxy_score: float = 0.0
    vpn_detected: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class DeviceFingerprintIndex:
    DEVICE_PREFIX = "dfp"
    USER_DEVICE_PREFIX = "ud"
    DEVICE_TXN_PREFIX = "dtx"

    def __init__(self, redis_client):
        self.redis = redis_client

    def _device_key(self, device_id: str) -> str:
        return f"{self.DEVICE_PREFIX}:{device_id}"

    def _user_device_key(self, user_id: str) -> str:
        return f"{self.USER_DEVICE_PREFIX}:{user_id}"

    def _device_txn_key(self, device_id: str) -> str:
        return f"{self.DEVICE_TXN_PREFIX}:{device_id}"

    async def register(
        self,
        device_id: str,
        user_id: str,
        fingerprint: DeviceFingerprint,
    ):
        fingerprint.user_id = user_id
        fingerprint.last_seen = datetime.now(UTC)
        features = fingerprint.to_features()
        feature_set = set(features)

        existing_raw = await self.redis.hgetall(self._device_key(device_id))
        is_new = not existing_raw

        mapping = {
            "user_id": user_id,
            "user_agent": fingerprint.user_agent or "",
            "features": json.dumps(list(feature_set)),
            "fingerprint_hash": fingerprint.fingerprint_hash(),
            "first_seen": fingerprint.first_seen.isoformat(),
            "last_seen": fingerprint.last_seen.isoformat(),
            "canvas_hash": fingerprint.canvas_hash or "",
            "webgl_hash": fingerprint.webgl_hash or "",
            "audio_hash": fingerprint.audio_hash or "",
        }
        await self.redis.hmset(self._device_key(device_id), mapping)

        await self.redis.sadd(self._user_device_key(user_id), device_id)

        txn_id = f"reg_{int(time.time())}"
        await self.redis.zadd(
            self._device_txn_key(device_id),
            {txn_id: time.time()},
        )
        await self.redis.expire(self._device_txn_key(device_id), 86400)

        return is_new

    async def lookup(self, device_id: str) -> DeviceFingerprint | None:
        data = await self.redis.hgetall(self._device_key(device_id))
        if not data:
            return None
        features = json.loads(data.get("features", "[]"))
        fp = DeviceFingerprint(device_id=device_id)
        fp.user_id = data.get("user_id")
        fp.user_agent = data.get("user_agent")
        for f in features:
            if f.startswith("ip:"):
                fp.ip_address = f[3:]
            elif f.startswith("ua:"):
                pass
            elif f.startswith("screen:"):
                fp.screen_resolution = f[7:]
            elif f.startswith("tz:"):
                fp.timezone = f[3:]
            elif f.startswith("lang:"):
                fp.language = f[5:]
            elif f.startswith("canvas:"):
                fp.canvas_hash = f[7:]
            elif f.startswith("webgl:"):
                fp.webgl_hash = f[6:]
            elif f.startswith("audio:"):
                fp.audio_hash = f[6:]
        if data.get("first_seen"):
            fp.first_seen = datetime.fromisoformat(data["first_seen"])
        if data.get("last_seen"):
            fp.last_seen = datetime.fromisoformat(data["last_seen"])
        return fp

    async def get_devices_for_user(self, user_id: str) -> list[str]:
        members = await self.redis.smembers(self._user_device_key(user_id))
        return list(members)

    async def compute_jaccard(self, device_id_a: str, device_id_b: str) -> float:
        a_raw = await self.redis.hgetall(self._device_key(device_id_a))
        b_raw = await self.redis.hgetall(self._device_key(device_id_b))
        if not a_raw or not b_raw:
            return 0.0
        a_features = set(json.loads(a_raw.get("features", "[]")))
        b_features = set(json.loads(b_raw.get("features", "[]")))
        union = a_features | b_features
        if not union:
            return 0.0
        return round(len(a_features & b_features) / len(union), 4)

    async def detect_multi_device(self, user_id: str) -> int:
        devices = await self.get_devices_for_user(user_id)
        return len(devices)

    async def is_emulator(self, device_id: str) -> bool:
        fp = await self.lookup(device_id)
        if not fp:
            return False
        emulator_indicators = [
            "Emulator",
            "Android SDK",
            "Genymotion",
            "BlueStacks",
            "NoxPlayer",
            "LDPlayer",
            "MuMuPlayer",
            "iPadian",
        ]
        if fp.user_agent:
            for indicator in emulator_indicators:
                if indicator.lower() in fp.user_agent.lower():
                    return True
        return False

    async def get_device_features(self, device_id: str, user_id: str) -> DeviceFeatures:
        features = DeviceFeatures(device_id=device_id, user_id=user_id)

        devices = await self.smembers(self._user_device_key(user_id))
        features.multi_device_count = max(1, len(devices))

        if devices and len(devices) > 1:
            similarities = []
            for other in devices:
                if other != device_id:
                    sim = await self.compute_jaccard(device_id, other)
                    similarities.append(sim)
            features.jaccard_similarity = max(similarities) if similarities else 1.0
        else:
            features.jaccard_similarity = 1.0

        features.is_emulator = await self.is_emulator(device_id)
        features.new_device_flag = not await self.redis.exists(self._device_key(device_id))

        txn_key = self._device_txn_key(device_id)
        features.txn_count_last_24h = await self.redis.zcount(txn_key, time.time() - 86400, time.time())

        await self._compute_proxy_score(features, device_id)

        return features

    async def _compute_proxy_score(self, features: DeviceFeatures, device_id: str):
        fp = await self.lookup(device_id)
        if not fp:
            return
        proxy_indicators = [
            "proxy", "vpn", "tor", "cloud", "datacenter",
        ]
        score = 0.0
        if fp.ip_address:
            for indicator in proxy_indicators:
                if indicator in fp.ip_address.lower():
                    score += 0.25
        if fp.timezone and fp.ip_address:
            score += 0.1
        features.proxy_score = round(min(score, 1.0), 2)
        features.vpn_detected = score > 0.5

    async def smembers(self, key: str) -> set:
        return await self.redis.smembers(key)


class DeviceFeatureExtractor:
    def __init__(self, index: DeviceFingerprintIndex):
        self.index = index

    async def extract(self, device_id: str, user_id: str) -> dict:
        features = await self.index.get_device_features(device_id, user_id)
        return {
            "device_is_emulator": int(features.is_emulator),
            "device_is_rooted": int(features.is_rooted),
            "device_is_spoofed": int(features.is_spoofed),
            "device_multi_device_count": features.multi_device_count,
            "device_jaccard_similarity": features.jaccard_similarity,
            "device_txn_count_24h": features.txn_count_last_24h,
            "device_distinct_users_24h": features.distinct_users_last_24h,
            "device_new_flag": int(features.new_device_flag),
            "device_proxy_score": features.proxy_score,
            "device_vpn_detected": int(features.vpn_detected),
        }
