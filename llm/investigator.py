import json
import os
import re

import ollama
from jinja2 import Template


class LLMInvestigator:
    def __init__(self, model: str | None = None, temperature: float = 0.1, base_url: str | None = None):
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.temperature = temperature
        self.client = ollama.Client(host=base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        self._load_prompt_template()

    def _load_prompt_template(self):
        with open("llm/prompts/fraud_narrative.txt") as f:
            self.template = Template(f.read())

    def investigate(self, evidence: dict) -> dict:
        alerts = self._build_alerts(evidence)
        prompt = self.template.render(alerts=alerts)

        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            options={"temperature": self.temperature},
        )

        narrative = response.get("response", "").strip()
        parsed = self._parse_narrative(narrative, evidence)

        return parsed

    def _build_alerts(self, evidence: dict) -> list[str]:
        alerts = []
        triggered = evidence.get("layer1_rules", [])
        for rule in triggered:
            alerts.append(f"Rule triggered: {rule}")

        gnn = evidence.get("gnn_explanation", {})
        if gnn:
            prob = gnn.get("fraud_probability", 0)
            alerts.append(f"GNN fraud probability: {prob:.3f}")
            subgraph = gnn.get("evidence_subgraph", [])
            alerts.extend(subgraph[:3])

        chi2 = evidence.get("layer1_chi2")
        if chi2 and chi2 > 0:
            alerts.append(f"Benford chi-squared: {chi2:.2f}")

        return alerts

    def _parse_narrative(self, narrative: str, evidence: dict) -> dict:
        narrative_clean = re.sub(r'[^\x20-\x7E\n.]', '', narrative).strip()

        fraud_prob = evidence.get("gnn_explanation", {}).get("fraud_probability", 0.5)

        if any(kw in narrative_clean.lower() for kw in ["mule", "ring", "cycling"]):
            fraud_type = "MULE_RING"
        elif any(kw in narrative_clean.lower() for kw in ["burst", "velocity", "rapid"]):
            fraud_type = "BURST_ATTACK"
        elif any(kw in narrative_clean.lower() for kw in ["collusion", "benford", "shell", "merchant"]):
            fraud_type = "MERCHANT_COLLUSION"
        elif any(kw in narrative_clean.lower() for kw in ["takeover", "ato", "login", "geo"]):
            fraud_type = "ATO"
        else:
            fraud_type = "OTHER"

        if fraud_prob > 0.85:
            action = "Block transaction and freeze account for review"
        elif fraud_prob > 0.5:
            action = "Flag for manual review within 4 hours"
        else:
            action = "No action required"

        return {
            "narrative": narrative_clean or "No narrative generated",
            "fraud_type": fraud_type,
            "confidence": round(max(0.5, min(0.99, fraud_prob + 0.1)), 4),
            "recommended_action": action,
        }
