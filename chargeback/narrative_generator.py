"""Chargeback narrative generation (Track 02 - Phase 10).

Reuses PayShield's existing LLM infrastructure (``llm.client.OllamaClient``)
with a chargeback-specific Jinja2 prompt template. The generator is
resilient:

- LLM unavailable  -> deterministic ``fallback()`` narrative built from the
  evidence facts (never an empty story, never a fake one).
- LLM output noisy -> tolerant JSON extraction; anything unparseable falls
  back to the deterministic narrative.
"""

import json
import logging
import re
from inspect import isawaitable
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader

from api.schemas.chargeback import EvidenceBundle, InvestigationNarrative

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path("chargeback/templates")
DEFAULT_TEMPLATE = "rebuttal_narrative.txt"


class NarrativeGenerator:
    """Builds the LLM prompt, calls the client and parses results."""

    def __init__(
        self,
        llm_client=None,
        template_dir: Path | str = DEFAULT_TEMPLATE_DIR,
        template_name: str = DEFAULT_TEMPLATE,
        model_name: str = "llama3.1:8b",
        temperature: float = 0.3,
        max_tokens: int = 800,
    ):
        self.llm_client = llm_client
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._env = Environment(loader=FileSystemLoader(str(template_dir)))
        self._template = self._env.get_template(template_name)

    # ------------------------------------------------------------------ #

    def build_prompt(
        self,
        evidence: EvidenceBundle,
        reason_code: str,
        reason_description: str,
        response_type: str,
    ) -> str:
        """Render the chargeback narrative prompt (Jinja2)."""
        facts = self.evidence_facts(evidence)
        return self._template.render(
            dispute=reason_code,
            dispute_description=reason_description,
            response_type=response_type,
            evidence_blob=self._render_facts(facts),
            response_type_map={
                "ACCEPT": "accept",
                "REJECT": "reject (contest)",
                "PARTIAL": "partially accept",
            }.get(response_type, response_type),
        )

    @staticmethod
    def evidence_facts(evidence: EvidenceBundle) -> list[dict[str, str]]:
        """Flatten the bundle into (type, description) facts for prompting."""
        facts: list[dict[str, str]] = []
        v = evidence.velocity_evidence
        if v:
            facts.append({"type": "velocity", "text": v.explanation})
        g = evidence.geo_evidence
        if g:
            facts.append({"type": "geography", "text": g.explanation})
        b = evidence.benford_evidence
        if b and b.chi2_statistic is not None:
            facts.append(
                {"type": "benford", "text": f"chi2={b.chi2_statistic:.2f} over {b.total_transactions} txns"}
            )
        gr = evidence.graph_evidence
        if gr:
            facts.append({"type": "graph", "text": f"gnn score {gr.gnn_score:.3f} anomaly={gr.anomaly_type or 'none'}"})
        l3 = evidence.investigation_report
        if l3:
            facts.append({"type": "investigation", "text": l3.summary})
        tp = evidence.transaction_proof
        if tp:
            facts.append(
                {"type": "transaction", "text": f"{tp.payment_method} {tp.amount} {tp.currency} at {tp.txn_timestamp.isoformat()}"}
            )
        dev = evidence.device_fingerprint
        if dev:
            facts.append(
                {"type": "device", "text": f"device={dev.device_id} new={dev.is_new_device}"}
            )
        me = evidence.merchant_evidence
        if me and me.delivery_proof:
            dp = me.delivery_proof
            facts.append(
                {"type": "delivery",
                 "text": f"{dp.courier_company} tracking={dp.tracking_id} delivered_at={dp.delivered_at}"}
            )
        if me and me.customer_communication:
            facts.append(
                {"type": "communication", "text": "; ".join(c.summary for c in me.customer_communication)}
            )
        for att in evidence.attachments:
            facts.append({"type": "attachment", "text": f"{att.evidence_type}: {att.url}"})
        return facts

    @staticmethod
    def _render_facts(facts: list[dict[str, str]]) -> str:
        if not facts:
            return "- (no evidence collected)"
        return "\n".join(f"- [{f['type']}] {f['text']}" for f in facts)

    # ------------------------------------------------------------------ #

    def parse(self, raw_text: str) -> InvestigationNarrative | None:
        """Extract a valid narrative JSON blob from LLM output."""
        for candidate in self._json_candidates(raw_text):
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            if "summary" in data or "full_report" in data:
                return InvestigationNarrative(
                    summary=str(data.get("summary", ""))[:2000],
                    full_report=str(data.get("full_report", ""))[:6000],
                    key_evidence=[str(k) for k in data.get("key_evidence", [])][:12],
                    quality_score=max(0.0, min(1.0, float(data.get("quality_score", 0.0)))),
                )
        return None

    @staticmethod
    def _json_candidates(raw_text: str) -> list[str]:
        candidates = []
        m = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if m:
            candidates.append(m.group(0))
        matches = re.findall(r"(\{(?:[^{}]|(?:\{[^{}]*\}))*\})", raw_text, re.DOTALL)
        candidates.extend(reversed(matches))
        return candidates

    @staticmethod
    def fallback(
        evidence: EvidenceBundle,
        reason_code: str,
        reason_description: str,
    ) -> InvestigationNarrative:
        """Deterministic narrative from evidence facts (no LLM)."""
        facts = NarrativeGenerator.evidence_facts(evidence)
        key_evidence: list[str] = []
        for f in facts:
            if f["type"] in ("velocity", "geography", "graph", "delivery", "communication"):
                key_evidence.append(f"{f['type']}: {f['text']}")
        summary = (
            f"Transaction evidence supports the {reason_description or reason_code} dispute "
            f"assessment: {len(key_evidence)} independent evidence points were "
            f"retrieved from PayShield's tamper-evident audit chain."
        )
        full_report = "\n".join(f"- [{f['type']}] {f['text']}" for f in facts) or "No evidence facts."
        return InvestigationNarrative(
            summary=summary[:2000],
            full_report=full_report[:6000],
            key_evidence=key_evidence[:12],
            quality_score=0.5,
        )

    # ------------------------------------------------------------------ #

    async def generate(
        self,
        evidence: EvidenceBundle,
        reason_code: str,
        reason_description: str,
        response_type: str,
    ) -> InvestigationNarrative:
        """Full pipeline: prompt -> LLM -> parse, with graceful fallback."""
        if self.llm_client is None:
            logger.debug("narrative LLM unavailable; using deterministic fallback")
            return self.fallback(evidence, reason_code, reason_description)
        try:
            prompt = self.build_prompt(evidence, reason_code, reason_description, response_type)
            generate = getattr(self.llm_client, "generate", None)
            if generate is None:
                return self.fallback(evidence, reason_code, reason_description)
            raw = generate(prompt, temperature=self.temperature, max_tokens=self.max_tokens)
            if isawaitable(raw):
                raw = await raw
            if isinstance(raw, dict):
                raw = json.dumps(raw)
            narrative = self.parse(raw) if isinstance(raw, str) else None
            if narrative is None:
                return self.fallback(evidence, reason_code, reason_description)
            return narrative
        except Exception as e:
            logger.warning("narrative generation failed: %s", e)
            return self.fallback(evidence, reason_code, reason_description)
