import asyncio
import logging
import time

import aiohttp
import requests

from llm.config import OllamaConfig

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, config: OllamaConfig | None = None):
        self.config = config or OllamaConfig()

    async def generate(self, prompt: str, max_tokens: int | None = None,
                       temperature: float | None = None) -> str:
        url = f"{self.config.base_url}/api/generate"
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
            },
        }
        for attempt in range(self.config.max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload,
                                            timeout=aiohttp.ClientTimeout(total=self.config.timeout)) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            logger.warning(f"Ollama generate failed (attempt {attempt + 1}): {resp.status} {text}")
                            if attempt < self.config.max_retries:
                                await asyncio.sleep(self.config.base_delay * (2 ** attempt))
                            continue
                        data = await resp.json()
                        return data.get("response", "")
            except asyncio.TimeoutError:
                logger.warning(f"Ollama generate timeout (attempt {attempt + 1})")
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.base_delay * (2 ** attempt))
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"Ollama generate connection error (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.base_delay * (2 ** attempt))
                continue
        return "LLM investigation unavailable"

    def generate_sync(self, prompt: str, max_tokens: int | None = None,
                      temperature: float | None = None) -> str:
        url = f"{self.config.base_url}/api/generate"
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens or self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
            },
        }
        for attempt in range(self.config.max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.config.timeout)
                if resp.status_code != 200:
                    logger.warning(f"Ollama generate_sync failed (attempt {attempt + 1}): {resp.status_code} {resp.text[:200]}")
                    if attempt < self.config.max_retries:
                        time.sleep(self.config.base_delay * (2 ** attempt))
                    continue
                data = resp.json()
                return data.get("response", "")
            except requests.RequestException as e:
                logger.warning(f"Ollama generate_sync error (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries:
                    time.sleep(self.config.base_delay * (2 ** attempt))
                continue
        return "LLM investigation unavailable"

    async def health(self) -> bool:
        url = f"{self.config.base_url}/api/tags"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        return False
                    data = await resp.json()
                    models = data.get("models", [])
                    available = any(self.config.model in (m.get("name", "") or "") for m in models)
                    if not available:
                        logger.info(f"Model {self.config.model} not found in Ollama")
                    return available
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    def health_sync(self) -> bool:
        url = f"{self.config.base_url}/api/tags"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = data.get("models", [])
            available = any(self.config.model in (m.get("name", "") or "") for m in models)
            if not available:
                logger.info(f"Model {self.config.model} not found in Ollama")
            return available
        except requests.RequestException:
            return False

    async def pull_model(self, model_name: str | None = None) -> bool:
        model = model_name or self.config.model
        url = f"{self.config.base_url}/api/pull"
        payload = {"model": model, "stream": False}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status == 200:
                        logger.info(f"Model {model} pulled successfully")
                        return True
                    text = await resp.text()
                    logger.error(f"Failed to pull model {model}: {resp.status} {text}")
                    return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Error pulling model {model}: {e}")
            return False
