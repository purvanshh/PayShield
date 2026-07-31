import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    fallback_model: str = "llama3.1:8b-instruct-q4_0"
    timeout: int = 300
    max_retries: int = 2
    base_delay: float = 1.0
    max_tokens: int = 256
    temperature: float = 0.1

    def __post_init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", self.base_url)
        self.model = os.getenv("OLLAMA_MODEL", self.model)

    @classmethod
    def from_yaml(cls, path: str | Path = "configs/config.yaml") -> "OllamaConfig":
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        ollama_cfg = data.get("ollama", {})
        return cls(
            base_url=ollama_cfg.get("base_url", cls.base_url),
            model=ollama_cfg.get("model", cls.model),
            fallback_model=ollama_cfg.get("fallback_model", cls.fallback_model),
            timeout=ollama_cfg.get("timeout", cls.timeout),
            max_retries=ollama_cfg.get("max_retries", cls.max_retries),
            base_delay=ollama_cfg.get("base_delay", cls.base_delay),
            max_tokens=ollama_cfg.get("max_tokens", cls.max_tokens),
            temperature=ollama_cfg.get("temperature", cls.temperature),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
