# Judge Q&A Playbook

20+ probable questions with the concise, *accurate* answers. Every number
below is sourced — quote the source out loud when you can.

---

## Transaction scoring

**Q: Why is the clean transaction score low?**
A: L1 velocity (3 txns in the hour, well under thresholds), geo Mumbai→Mumbai
(0 km/h displacement), Benford normal; L2 GNN conditional — for this user it
ran and returned 0.12. The ensemble reads 0.08–0.15 for this profile. Source:
`docs/DEMO_DATA.md`, Scenario 1.

**Q: Why does L2 skip for new users?**
A: GNN needs graph context — a user with <2 nodes has no neighbor
information. We return `SKIPPED_NO_GRAPH` and fall back to L1-only fusion.
It's a deliberate availability choice: we don't block the hot path for a
model with no signal.

**Q: What are the latency facts?**
A: L1 filter p99 0.27 ms (measured in the reported baseline); full pipeline
with L2 ~15 ms; LLM narration is async via Celery (~35 s) and never blocks
the decision. Chargeback rebuttal assembly is well under 100 ms — the API
reports `latency_ms` in the response.

**Q: How do you know L2 is working?**
A: Measured, not assumed: v1.1 PR-AUC 0.4125 (4× the edge-free baseline),
gate at +0.005 PR-AUC for promotion, drift monitoring via PSI from the
feature registry.

## Return risk

**Q: Why is the serial-returner order 0.83?**
A: Arithmetic, public in the response: weighted contributions 0.5775
(rate 0.165 + serial flag 0.20 + merchant 0.045 + category 0.045 + amount
0.055 + COD-refusal 0.0375 + velocity 0.03), plus a capped rule adjustment
+0.25 from five fired rules. See `docs/DEMO_DATA.md` Scenario 3.

**Q: Why weighted scoring and not a trained classifier?**
A: We have no real merchant return labels; weighting is explainable to a
merchant, tunable via YAML without a redeploy/retrain, and rules provide
hard guardrails. When real labels exist, the same feature surface can back
a classifier — the registry is the contract either way.

**Q: How were weights chosen?**
A: Domain-first: user history dominates (0.25+0.20), then merchant/category
context (0.15 each), amount and COD-refusal 0.10, velocity 0.05 — they sum
to 1.0 and live in `configs/feature_registry_return.yaml`. We validated on
held-out data (see next).

**Q: What's the honest false-positive story?**
A: At the HIGH cut precision is 1.0 (zero FPs) but recall 0.37 — that cut
under-fires; at the MEDIUM+ cut precision 0.944, recall 0.913. FPs are
casual returners ordering fashion — which is why MEDIUM's action is
FLAG_FOR_REVIEW, not BLOCK.

**Q: Why PR-AUC as the lead metric?**
A: The positive class is 40% here, so ROC-AUC can look inflated; PR-AUC
measures the minority class directly — it's the metric that corresponds to
"how many flagged orders were actually bad".

## Chargeback response

**Q: How do you know the Razorpay payload is right?**
A: It's mapped to the disputes API contract documented in
`docs/reference/chargeback_protocols.md` (contest flag + evidence slots with
`{type: document, url, description}`). The payload is built in exactly one
method (`_build_razorpay_payload`) so a field rename touches one place;
mock mode validates shape; production verification against Razorpay's test
environment is the one unverified step, stated plainly.

**Q: Why is the winnable dispute REJECT with high confidence?**
A: Completeness is 1.0 — transaction proof + device record + audit
reconstruction of a clean L1 pass. Confidence = completeness + rejection
boost (capped at 1.0). The confidence is asserted *by construction* and the
audit trail shows exactly which evidence was retrieved.

**Q: What happens when evidence is incomplete?**
A: The weak case: new user, no device record, no graph/L3 → completeness
0.68, conservative PARTIAL, warnings "graph evidence incomplete" and "LLM
report unavailable". We'd rather lose the dispute than fabricate evidence.

**Q: Why rule-based response type, not ML?**
A: ACCEPT/REJECT/PARTIAL is governed by evidence availability — a legal
claim, not a probability. Rules are auditable in a dispute hearing; an ML
verdict would need a different justification than the evidence list. We
chose explainability over nuance here on purpose.

**Q: When does the system actually submit?**
A: Never automatically by default. `/respond` produces a draft; `/submit`
is a separate call gated on `chargeback:admin` (human-in-the-loop), and
auto-submit in `/respond` requires the same permission. RBI/oversight
compliance relies exactly on this separation.

## Architecture & compliance

**Q: How does the tamper-evident audit log work?**
A: Append-only JSONL hashes every entry, each referencing the previous hash
— chain verification is `verify_chain()`. PII is masked by key before
writing. Every chargeback/return event lands there; the evidence collector
reads from it, so rebuttals are reconstructions, not re-analyses.

**Q: What's the difference between fraud score, return risk, chargeback?**
A: Reactive (fraud at the transaction), proactive (return risk before
dispatch), remedial (evidence after a dispute). One audit chain, three
merchant-facing decisions.

**Q: Is everything defense-only?**
A: Yes — no automated contest submission (admin gate), no reverse lookup or
"offense-capable" calls. The one write path (`/v1/return/update`) only
records events merchants already caused.

**Q: What about EU AI Act / RBI specifics?**
A: Measured: PCI-DSS 90/100, RBI 83/100 (passing), EU AI Act 100/100 with the
configured runtime env (`COMPLIANCE_DELTA_TRACK2.md`). Controls map to
concrete code: RBAC per route, HMAC-verified webhook, feature breakdown in
every score response, weights/rules public YAML, confidence with graceful
degradation.

**Q: Where does the graph evidence come from in real life?**
A: The GNN runs on the heterogeneous user/merchant/device graph; for the
chargeback responder the *stored* score from transaction time is read — we
never re-infer at dispute time, which is what keeps the rebuttal honest.

## Closing

**Q: Why does this deserve to win?**
A: It's a production-shaped system that a small merchant can operate: an
explicit three-act story (reactive/proactive/remedial), honest metrics at
two operating points, compliance evidence for every control, and graceful
failure shown on camera — not in the appendix.
