import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)


class MemoryAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="memory_agent", agent_type="MEMORY"))
        self._patterns: list[dict] = []
        self._index: dict[str, list[int]] = {}

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "STORE_PATTERN":
            return await self._handle_store(message)
        elif msg_type == "RETRIEVE_PATTERNS":
            return await self._handle_retrieve(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_store(self, message: AgentMessage) -> AgentMessage:
        pattern = message.content.get("pattern", "")
        metadata = message.content.get("metadata", {})
        pattern_id = self._store_pattern(pattern, metadata)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "stored", "pattern_id": pattern_id},
            correlation_id=message.message_id,
        )

    async def _handle_retrieve(self, message: AgentMessage) -> AgentMessage:
        query = message.content.get("query", "")
        k = message.content.get("k", 5)
        results = self._retrieve_patterns(query, k)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "retrieved", "patterns": results, "count": len(results)},
            correlation_id=message.message_id,
        )

    def _store_pattern(self, pattern: str, metadata: dict) -> str:
        pattern_id = hashlib.sha256(pattern.encode()).hexdigest()[:16]
        entry = {
            "pattern_id": pattern_id,
            "pattern": pattern,
            "metadata": metadata,
            "timestamp": datetime.utcnow().isoformat(),
            "embedding": self._compute_embedding(pattern),
        }
        self._patterns.append(entry)
        for keyword in self._extract_keywords(pattern):
            if keyword not in self._index:
                self._index[keyword] = []
            self._index[keyword].append(len(self._patterns) - 1)
        logger.info(f"Stored pattern {pattern_id}")
        return pattern_id

    def _retrieve_patterns(self, query: str, k: int) -> list[dict]:
        query_embedding = self._compute_embedding(query)
        scored = []
        for i, entry in enumerate(self._patterns):
            similarity = self._cosine_similarity(query_embedding, entry["embedding"])
            scored.append((similarity, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, entry in scored[:k]:
            result = {k: v for k, v in entry.items() if k != "embedding"}
            result["similarity"] = round(score, 4)
            results.append(result)
        return results

    def _compute_embedding(self, text: str) -> list[float]:
        words = text.lower().split()
        word_set = set(words)
        vector = [0.0] * 64
        for i, word in enumerate(sorted(word_set)[:64]):
            vector[i % 64] += words.count(word) / max(len(words), 1)
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        return dot

    def _extract_keywords(self, text: str) -> list[str]:
        keywords = {"mule", "burst", "velocity", "device", "merchant", "geo",
                    "benford", "shap", "graph", "cycle", "refund", "collusion",
                    "takeover", "fraud", "anomaly", "block", "escalate"}
        words = set(text.lower().split())
        return list(words & keywords)
