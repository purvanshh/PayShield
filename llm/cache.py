import hashlib
import json


class LLMCache:
    def __init__(self, redis_client, ttl: int = 86400):
        self.redis = redis_client
        self.ttl = ttl

    def _make_key(self, evidence: dict) -> str:
        raw = json.dumps(evidence, sort_keys=True)
        return f"llm_cache:{hashlib.sha256(raw.encode()).hexdigest()}"

    def get(self, evidence: dict) -> str | None:
        pass

    def set(self, evidence: dict, narrative: str):
        pass
