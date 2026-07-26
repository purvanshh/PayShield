import argparse
import asyncio
import logging

from llm.client import OllamaClient
from llm.config import OllamaConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Pull Ollama model for PayShield LLM Investigator")
    parser.add_argument("--model", default=None, help="Model name to pull (default: from config)")
    parser.add_argument("--fallback", action="store_true", help="Pull the fallback (quantized) model instead")
    args = parser.parse_args()

    config = OllamaConfig()
    client = OllamaClient(config)

    model = args.model or (config.fallback_model if args.fallback else config.model)
    logger.info(f"Checking health at {config.base_url}...")
    healthy = await client.health()
    if not healthy:
        logger.warning(f"Ollama not healthy at {config.base_url}")
        logger.info(f"Attempting to pull model {model}...")
    else:
        logger.info(f"Ollama healthy, model {model} not found, attempting pull...")

    success = await client.pull_model(model)
    if success:
        logger.info(f"Model {model} is ready")
    else:
        logger.error(f"Failed to pull model {model}")
        logger.info("Make sure Ollama is running at the configured base_url")


if __name__ == "__main__":
    asyncio.run(main())
