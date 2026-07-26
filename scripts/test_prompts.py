import argparse
import json
import logging

from llm.client import OllamaClient
from llm.config import OllamaConfig
from llm.prompt_builder import PromptBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SAMPLE_EVIDENCE = [
    {"type": "transaction_velocity", "description": "15 transactions in 5 minutes", "severity": "HIGH"},
    {"type": "device_fingerprint", "description": "Shared device across 12 users", "severity": "HIGH"},
    {"type": "graph_centrality", "description": "Connected to 8 flagged accounts", "severity": "MEDIUM"},
]

SAMPLE_SHAP = [
    {"name": "txn_count_5min", "value": 15.0, "shap_value": 0.42},
    {"name": "unique_devices", "value": 12.0, "shap_value": 0.35},
]

SAMPLE_GRAPH = [
    {"type": "user", "id": "U10023", "importance": 0.91},
    {"type": "device", "id": "D8841", "importance": 0.87},
]


async def main():
    parser = argparse.ArgumentParser(description="Test LLM prompts")
    parser.add_argument("--skip-ollama", action="store_true", help="Skip actual Ollama call")
    args = parser.parse_args()

    builder = PromptBuilder()
    version = builder.get_version()
    logger.info(f"Prompt version: {version}")

    prompt = builder.build_narrative_prompt(SAMPLE_EVIDENCE, SAMPLE_SHAP, SAMPLE_GRAPH)
    logger.info(f"Prompt length: {len(prompt)} chars")
    print("\n" + "=" * 60)
    print("GENERATED PROMPT:")
    print("=" * 60)
    print(prompt[:2000])
    if len(prompt) > 2000:
        print(f"\n... ({len(prompt) - 2000} more chars)")

    if not args.skip_ollama:
        config = OllamaConfig()
        client = OllamaClient(config)

        logger.info(f"Checking Ollama health at {config.base_url}...")
        healthy = await client.health()
        if not healthy:
            logger.warning("Ollama not healthy — skipping generation")
            logger.info("Run the pull script first: python scripts/pull_ollama_model.py")
            return

        logger.info("Generating narrative with Ollama...")
        response = await client.generate(prompt, max_tokens=512, temperature=0.1)
        print("\n" + "=" * 60)
        print("OLLAMA RESPONSE:")
        print("=" * 60)
        print(response)

        try:
            parsed = json.loads(response)
            print("\n" + "=" * 60)
            print("PARSED JSON:")
            print("=" * 60)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            logger.warning("Response was not valid JSON")

    print("\nDone.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
