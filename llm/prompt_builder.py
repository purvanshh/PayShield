import copy
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from jinja2 import Environment, FileSystemLoader, TemplateNotFound
    _has_jinja2 = True
except ImportError:
    Environment = None
    FileSystemLoader = None
    TemplateNotFound = Exception
    _has_jinja2 = False

PROMPTS_DIR = Path(__file__).parent / "prompts"
EXAMPLES_DIR = PROMPTS_DIR / "examples"
MANIFEST_PATH = PROMPTS_DIR / "manifest.yaml"

try:
    import yaml
except ImportError:
    yaml = None


class PromptManifest:
    def __init__(self, path: Path | None = None):
        self.path = path or MANIFEST_PATH
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 0}
        if yaml is None:
            return {"version": 0}
        with open(self.path) as f:
            return yaml.safe_load(f) or {}

    @property
    def version(self) -> int:
        return self.data.get("version", 0)

    @property
    def template_name(self) -> str:
        return self.data.get("template", "fraud_narrative.txt")

    @property
    def examples(self) -> list[str]:
        return self.data.get("few_shot_examples", [])


class PromptBuilder:
    def __init__(self, env: Any | None = None, manifest: PromptManifest | None = None):
        self.manifest = manifest or PromptManifest()
        self.env = env or self._create_env()
        self.template = self._load_template()
        self.examples: list[dict] = self._load_examples()

    def _create_env(self):
        if not _has_jinja2:
            logger.warning("Jinja2 not available; using raw template")
            return None
        return Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    def _load_template(self):
        if not _has_jinja2 or self.env is None:
            logger.warning("Jinja2 not available, cannot load template")
            return None
        try:
            return self.env.get_template(self.manifest.template_name)
        except TemplateNotFound:
            logger.error(f"Template {self.manifest.template_name} not found")
            return None

    def _load_examples(self) -> list[dict]:
        import json
        examples = []
        for name in self.manifest.examples:
            path = EXAMPLES_DIR / name
            if path.exists():
                with open(path) as f:
                    examples.append(json.load(f))
        logger.info(f"Loaded {len(examples)} few-shot examples")
        return examples

    def build_narrative_prompt(self, evidence: list[dict], shap_features: list[dict],
                               graph_nodes: list[dict]) -> str:
        if self.template is None:
            return self._fallback_prompt(evidence, shap_features, graph_nodes)
        base = self.template.render(
            evidence=evidence,
            shap_features=shap_features,
            graph_nodes=graph_nodes,
        )
        base = self._inject_examples(base)
        base = self._truncate_if_needed(base)
        return base

    def _inject_examples(self, prompt: str) -> str:
        if not self.examples:
            return prompt
        import json
        chunks = []
        for i, ex in enumerate(self.examples):
            expected = ex.get("expected_output", {})
            chunks.append(f"--- EXAMPLE {i + 1}: {ex.get('scenario', '')} ---")
            chunks.append("INPUT EVIDENCE:")
            chunks.append(json.dumps(ex.get("evidence", []), indent=2))
            chunks.append("\nEXPECTED OUTPUT:")
            chunks.append(json.dumps(expected, indent=2))
        examples_block = "\n".join(chunks)
        return examples_block + "\n\n--- NOW ANALYZE THE FOLLOWING ---\n\n" + prompt

    def _truncate_if_needed(self, prompt: str, max_chars: int | None = None) -> str:
        limit = max_chars or 4000
        if len(prompt) <= limit:
            return prompt
        logger.warning(f"Prompt length {len(prompt)} exceeds {limit}, truncating")
        truncated = prompt[:limit]
        last_newline = truncated.rfind("\n")
        if last_newline > limit * 0.8:
            truncated = truncated[:last_newline]
        return truncated

    def _fallback_prompt(self, evidence: list, shap_features: list, graph_nodes: list) -> str:
        import json
        lines = ["You are a senior fraud analyst. Analyze the fraud evidence.\n"]
        lines.append("EVIDENCE:")
        for item in evidence:
            lines.append(f"- {item.get('type', '?')}: {item.get('description', '?')} (severity: {item.get('severity', '?')})")
        lines.append("\nSHAP FEATURES:")
        for feat in shap_features:
            lines.append(f"- {feat.get('name', '?')}: {feat.get('value', '?')} (contribution: {feat.get('shap_value', '?')})")
        lines.append("\nGRAPH SUBGRAPH:")
        for node in graph_nodes:
            lines.append(f"- {node.get('type', '?')} {node.get('id', '?')}: importance {node.get('importance', '?')}")
        lines.append("\nOutput JSON with narrative, fraud_type, confidence, recommended_action, key_evidence, reasoning.")
        return "\n".join(lines)

    def get_version(self) -> int:
        return self.manifest.version
