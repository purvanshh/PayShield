"""Centralised Pydantic settings – single source of truth for all config.

Loads  *configs/config.yaml*  then allows every leaf value to be overridden
via an environment variable of the form  PAYSHIELD_{SECTION}_{KEY}  (upper,
underscore-separated).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class _YamlConfigLoader:
    """Loads the static YAML file once and flattens it for env injection."""

    _cached: dict[str, Any] | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> dict[str, Any]:
        if cls._cached is not None:
            return cls._cached

        path = path or Path("configs/config.yaml")
        if path.exists():
            with open(path, encoding="utf-8") as f:
                cls._cached = yaml.safe_load(f) or {}
        else:
            cls._cached = {}
        return cls._cached


def _env_override_for(prefix: str, section: str, key: str, default: Any) -> Any:
    """Look up PAYSHIELD_{SECTION}_{KEY} in the environment."""
    env_name = f"{prefix}_{section.upper()}_{key.upper()}"
    raw = os.getenv(env_name)
    if raw is None:
        return default

    # Coerce to the same type as the YAML default when possible
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


def _hydrate_section(prefix: str, section_name: str, yaml_values: dict[str, Any]) -> dict[str, Any]:
    """Return a dict where every leaf has been checked against env vars."""
    return {k: _env_override_for(prefix, section_name, k, v) for k, v in yaml_values.items()}


class ModelSettings(BaseSettings):
    hidden_channels: int = 64
    num_layers: int = 2
    dropout: float = 0.3
    pos_weight: int = 10


class ThresholdSettings(BaseSettings):
    block_probability: float = 0.85
    escalate_probability: float = 0.50
    benford_chi2_critical: float = 15.51
    min_benford_samples: int = 20
    velocity_zscore: float = 3.0
    geo_velocity_max_kmh: float = 900.0


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    velocity_ttl_seconds: int = 3600
    baseline_ttl_seconds: int = 86400

    @model_validator(mode="after")
    def _legacy_env_fallback(self):
        """Legacy REDIS_* env vars (used by docker-compose) win over YAML."""
        host = os.getenv("REDIS_HOST")
        if host:
            self.host = host
        port = os.getenv("REDIS_PORT")
        if port:
            self.port = int(port)
        db = os.getenv("REDIS_DB")
        if db:
            self.db = int(db)
        return self


class OllamaSettings(BaseSettings):
    model: str = "llama3.1:8b"
    temperature: float = 0.1
    base_url: str = "http://localhost:11434"

    @model_validator(mode="after")
    def _legacy_env_fallback(self):
        """Legacy OLLAMA_* env vars (used by docker-compose) win over YAML."""
        base_url = os.getenv("OLLAMA_BASE_URL")
        if base_url:
            self.base_url = base_url
        model = os.getenv("OLLAMA_MODEL")
        if model:
            self.model = model
        temperature = os.getenv("OLLAMA_TEMPERATURE")
        if temperature:
            self.temperature = float(temperature)
        return self


class FeatureDriftSettings(BaseSettings):
    psi_threshold: float = 0.25
    check_interval_minutes: int = 60


class Settings(BaseSettings):
    """Single source of truth for PayShield configuration.

    Priority (high → low):
        1. Environment variables   PAYSHIELD_*
        2. Values from configs/config.yaml
        3. Defaults declared below
    """

    model_config = SettingsConfigDict(
        env_prefix="PAYSHIELD_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    model: ModelSettings = Field(default_factory=ModelSettings)
    thresholds: ThresholdSettings = Field(default_factory=ThresholdSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    feature_drift: FeatureDriftSettings = Field(default_factory=FeatureDriftSettings)

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> "Settings":
        """Hydrate settings from YAML then allow env overrides."""
        yaml_data = _YamlConfigLoader.load(path)

        kwargs: dict[str, Any] = {}
        for section in ("model", "thresholds", "redis", "ollama", "feature_drift"):
            yaml_section = yaml_data.get(section, {})
            hydrated = _hydrate_section("PAYSHIELD", section, yaml_section)
            kwargs[section] = hydrated

        return cls(**kwargs)


# Global singleton – imported everywhere
settings = Settings.from_yaml()
