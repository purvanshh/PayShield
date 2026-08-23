# Panel Prep — 30 Questions, Answered from the Source

Everything below is calibrated to what the code actually does — every
number traces to a measured artifact (benchmark JSON, quality-gate report,
demo-data verification, docs/DEMO_DATA.md). If a claim has no source, it
says so. Corroborate while answering: "the exact run is in
`models/return_risk_benchmark_results.json`".

## Architecture & Design (Q1–Q10)

**Q1 — Why rules for the chargeback verdict, not a classifier?**

Because ACCEPT/REJECT/PARTIAL is an evidence-governance problem, not a
prediction: with a signed POD on a 13.1, you contest; with no evidence,
accepting is cheaper than contesting a sure loss. A rule table is auditable
in a dispute hearing; a weight matrix is not. Where ambiguity genuinely
exists (completeness between 0.5 and 0.8), the response is PARTIAL with
warnings plus a confidence number — the merchant's decision inputs. Trade-off
acknowledged in `docs/DESIGN_DECISIONS.md` §2.

**Q2 — Walk me through a chargeback webhook end-to-end.**

POST `/webhooks/razorpay/chargeback` → constant-time HMAC-SHA256 check over
the raw body (`chargeback/signatures.py`) → dispute marker + audit append →
if the payment→txn mapping exists (`chargeback:payment_txn:{payment_id}`,
written by `respond`), the background task runs the same collector+builder
pipeline the API uses and caches the draft (`chargeback:rebuttal:{dispute_id}`,
30d TTL). Nothing is submitted automatically — submission is a separate
admin-only call. Evidence is *reconstructed* from the hash-chained audit
JSONL, never re-analysed.

**Q3 — Redis down during return-risk scoring?**

Every store read flows through `_safe_redis` → neutral defaults with
`default_redis_error` provenance tags (visible in the API breakdown), no
retry loop, bounded score, rules evaluate on a flat profile (none fire).
Chaos experiment: `tests/chaos/test_chaos_track2.py::TestRedisOutageReturnRisk`.
The 500-free path is also the *masked-device* path taught earlier — the
audit chain masks device IDs by design, so lookups resolve through the
`ud:{user_id}` index.

**Q4 — How did you pick the weights?**

Domain-first: user history dominates (0.25 + 0.20), merchant/category
context (0.15 each), then amount/COD-refusal/velocity (0.10/0.10/0.05; they
sum to 1.0). Lives in `configs/feature_registry_return.yaml`; tune without
redeploy. Verification is the benchmark: **PR-AUC 0.9806**, precision 1.0000
at the strict gate, 0.9444/0.9125 at the review gate. Honest admission: with
no real merchant labels the weights are validated on realistic archetypes —
labelled data would let us train the same feature surface, and the
reflection/A-B loop exists for exactly that migration.

**Q5 — Why PR-AUC as the lead metric?**

Because the positive class is 40% here, and 90% accuracy can be achieved by
predicting "safe" for everything. PR-AUC scores the minority class directly.
We publish ROC-AUC too (0.9846) plus operating points at both shipped tier
cuts — see `reports/return_risk_benchmark_report.md`.

**Q6 — UPI vs Visa handling?**

Deadlines: UPI window 7d, Visa/MC 30d, Amex 20, RuPay 15
(`response_deadline_days`, public in config). The urgency field reports the
fraction of the network window elapsed. Reason classes: 10.4/10.5/FRAUD/
UNAUTHORIZED are fraud-class (REJECT only at high completeness), 13.1/13.2/
SERVICES_NOT_PROVIDED are service-class (delivery proof decides). The
network string rides into the document for the narrative prompt. (The plan's
"7d vs 30d" distinction is exactly our `_get_response_window`.)

**Q7 — Audit-log tamper resistance?**

Append-only JSONL (`store/audit_log.py`): every entry carries
`prev_hash` and `hash` (SHA-256 over the canonical JSON), `entry_id`,
timestamp, masked actor, PII-masked payload. `verify_chain()` recomputes
every hash; any retroactive edit breaks the chain at its point. It is
file-based by design (POSIX append semantics, no DB to corrupt); production
would add write-once storage or SIEM shipping, and the docstring says so.
PII masking happens *before* hashing — that is the subtlety worth
mentioning (masks are part of the artefact, not applied on read).

**Q8 — Fraud score vs return-risk score vs chargeback confidence?**

Fraud score (reactive, at the transaction) *is* a probability from ensemble
fusion. Return-risk score (proactive, pre-dispatch) is a weighted composite
plus capped rule adjustment — a risk ordering, with the arithmetic public.
Chargeback confidence (remedial) is **not** a probability at all: it's
completeness-based (evidence available ÷ evidence needed) with a rejection
boost; 0.92 means "the evidence case is strong", 0.6 means "thin — the
response must own it".

**Q9 — Resource footprint?**

No load run exists against the live stack — the Locust harness is ready
(`tests/load/return_risk_loadfile.py`) but the numbers are yours to produce
(see `docs/LOAD_TESTING.md` for the honest template). What *is* measured:
hot-path L1 p99 0.27ms (repo baseline), full-track-2 response times reported
per request via `latency_ms`, in-process benchmark timing in
`reports/perf_optimization`. Oligarchic guesses are worse than "not
measured yet — here's the harness".

**Q10 — One more week?**

Real merchant/sandbox data for label validation; cross-merchant return
fraud in the graph layer (a privacy-preserving ask — the graph schema
already has merchant edges); and chargeback-outcome webhooks feeding the
reflection loop (the outcome matrix analyser already exists in
`agents/risk_suite_reflection.py` — it's waiting on data, not code).

## Code quality (Q11–Q20)

**Q11 — Show the L2-missing test.**

`tests/integration/test_chargeback_flow.py::test_incomplete_evidence_is_conservative`
(plus the earlier `test_evidence_collector` unit suite): audit entry with no
device/no rules → completeness 0.62, PARTIAL, warnings in the response,
confidence below the 0.7 gate — 200, never 500. The collector path is the
same one that previously lost *all* devices to masking (see Q3).

**Q12 — How do you know the Razorpay payload is right?**

It's mapped to the disputes contract in
`docs/reference/chargeback_protocols.md` (contest flag + evidence slots
`{type, url, description}`), built in exactly one method
(`_build_razorpay_payload`) so a field rename touches one line, and the
documented verification gap ("Razorpay's live response codec needs checking
with a real sandbox key") is written out — not hidden. Mock mode is a
*contract* tool, not a crutch.

**Q13 — Chargeback module coverage?**

91.1% across chargeback/, return_risk/, new routes/schemas (from
`reports/quality_gate_track2.md`); module-level: rebuttal_builder 99%,
narrative_generator 90%, evidence_collector 79% (provider + artifact paths),
razorpay_client 81%. The gaps are transport-error branch variants, covered
by chaos tests instead.

**Q14 — CI?**

`make test` (578 hermetic tests), `make lint` (ruff), targeted mypy strict
on chargeback/return_risk, bandit on the risk modules, compliance checkers.
GitHub Actions exist for retrain; the CI workflow predates Track 2 — say
so, then show the gates being run.

**Q15 — Secrets?**

Env-only (compose defaults for dev: `ENCRYPTION_KEY`, dev key documented);
`.gitignore` covers `.env`, `store/audit_logs`, `node_modules`; no tracked
secrets (verified in the security audit this week — see Q43 report).

**Q16 — Most complex bug?**

Three real ones, all in `docs/APPLICATION_ANSWERS.md` §12; the best
whiteboard story is the *audit masking one* (evidence lookup returning
"no device" for every transaction until the READ side learned to resolve
masked IDs) — it's a correctness-through-schemas bug, not a syntax typo.

**Q17 — API versioning?**

Path versioning (`/v1/*` prefixes in `api/main.py`); agent versions in
`generated_by: chargeback_agent_v1.0.0`; schemas are the contract
(`api/schemas/chargeback.py`, OpenAPI fragments in `docs/reference/`).

**Q18 — Rollback?**

No blue-green in this repo. Config is the rollback primitive: weights,
thresholds and rules are YAML/Redis (no deploy needed); mock mode isolates
Razorpay changes; draft caches make retries idempotent (same payload re-
submitted after recovery — the chaos test proves no duplicate contest).

**Q19 — Monitoring?**

Prometheus (fraud, latency, chargeback/return counters + histograms),
structlog + correlation IDs, audit chain as the forensic layer, PSI drift
for both feature surfaces (`/admin/drift/psi`, `/admin/drift/return-risk`).
Grafana dashboard exists for the base stack. Tracing/alerting — documented
as future work, honestly.

**Q20 — Retention?**

Audit JSONL retained (compose named volume; 12-month PCI window noted in
docs); return-risk profiles TTL'd (90d config); rebuttal drafts 30d TTL;
PII masked at write. The "7-year RBI archive" claim in the base docs is an
aspiration — say "retention limits are configured, archival is ops work".

## Domain & regulations (Q21–Q30)

**Q21 — RBI timelines?** Limited-liability customer protection model: zero
liability on reported-early unauthorized debits, provisional credit windows
in days (not years), and UPI dispute response windows of days under NPCI's
DRF. Our urgency comes from per-network `response_deadline_days` — the
documented matrix is in `docs/reference/chargeback_protocols.md`.

**Q22 — EU AI Act?** Score 100/100 in the compose env
(`COMPLIANCE_DELTA_TRACK2.md`) — transparency (public weights/rules, feature
breakdown), oversight (draft/submit separation, admin gate), accuracy
(measured, both cuts), robustness (chaos tests), data governance (synthetic
data, no real PII).

**Q23 — PCI-DSS req 10?** Hash-chained, PII-masked, verifiable audit
(`store/audit_log.py`) — audit of *actions*, keys mapped to principals via
the auth layer; the checker scores 90/100 with the MFA control explained as
per-account TOTP (checker wants a static env flag).

**Q24 — "Your scorer is biased" playbook?** Show the feature breakdown
(merchant can verify against their own records), offer per-merchant tier
thresholds (config), run the champion/challenger experiment, run the
fairness audit (`models/fairness_audit.py`), and note every HIGH is a
recommendation with a logged override path. The AI advises — the merchant
decides.

**Q25 — Chargeback vs refund?** Refund = merchant-initiated, cooperative,
same money back. Chargeback = customer-initiated via their PSP, adversarial,
fees + escrow. Track 2 sits on both sides of the same loss: return-risk
reduces refunds, the responder contests chargebacks.

**Q26 — Defence-only proof?** (1) Design: the responder produces rebuttals
from *stored* evidence; nothing invents, fabricates or ships an offensive
capability; the only write path records merchant-caused events. (2) RBAC:
submission + auto-submit are `chargeback:admin`, tested in
`tests/integration/test_chargeback_api.py`. (3) Audit: every action is
chain-logged.

**Q27 — NPCI DRF vs Visa?** Category structures differ, but for a merchant
the operative difference is **timeline + evidence weight**; the schema
carries `network` + `reason_code` and the deadline map (7/30/20/15).
Visa/MC exact code tables are partially listed in the research doc with an
explicit "verify against current circular" caveat — the honest stance.

**Q28 — Currency?** INR-only by scope; the evidence bundle carries
`currency` on the transaction proof, and the doc notes the forex/12.3
extension path if internationalized.

**Q29 — Cost of a false positive?** Precision 1.0000 at the strict gate
means the prepaid gate never flags a safe order — its cost is *recall*
(0.37 of high-risk users slip to review). At the review gate, 5.6% of flags
are casual returners whose next-best action IS review; the report breaks
down exactly which archetypes mis-fire and why that's still the right action.

**Q30 — Why you?** 50 phases, a 3-layer risk suite with measured precision,
an audit story a compliance team can read, and the habit of saying "not
measured yet" out loud — the last one is the strongest signal.

---

## How to rehearse

1. Time each answer to a 45-second guardrail.
2. Say the metric **and** its source file, never just the number.
3. For anything not in this doc: don't backfill the truth — say "I'd
   approach it as …", which is what the panel is actually testing.
