# Design Decisions — Track 2

Why the risk suite looks the way it does: context, options considered,
chosen approach, trade-offs.

## 1. Reconstruct, don't re-analyse (chargeback evidence)

**Decision.** The evidence collector reads the tamper-evident audit chain
and Redis mirrors; it never re-runs L1/L2/L3 at dispute time.

**Rationale.** A rebuttal must reflect what the pipeline *knew at
transaction time*. Re-scoring a transaction two months later would mix
post-hoc information into a legal document — exactly the kind of
inconsistency a disputes officer would object to. The audit chain is
append-only and hash-chained, so the evidence we quote is provably the
original record.

**Options considered.** (a) Live re-inference (rejected: hindsight leaks,
latency, recompute cost on a hot path), (b) store a frozen JSON snapshot
per txn (closer, but duplication across systems), (c) read the chain as
the single source of truth (chosen: one store, tamper-evident by design).

**Trade-off.** We can't quote evidence the pipeline didn't capture (e.g.
no L3 if it hadn't finished). That is exactly why completeness scores and
low-confidence PARTIAL responses exist — the system's honesty is a
feature, not a bug.

## 2. Rules for the verdict, not a model (response type)

**Decision.** ACCEPT / REJECT / PARTIAL is rule-based (completeness
thresholds + evidence-type logic), not a learned classifier.

**Rationale.** A chargeback response is a claim about evidence existence,
not a probability: with a signed POD for a 13.1, you reject; without any
evidence, accepting (or partially acknowledging) is cheaper than
contesting a sure loss. Rules are auditable in a dispute hearing and
testable in a unit test; the decision logic is ~20 lines with explicit
precedence.

**Trade-off.** Less "smart" on ambiguous bundles. Mitigation: ambiguity is
bounded by construction — evidence either exists or it doesn't, and the
completeness number is the continuous part the merchant can improve by
attaching more proof.

## 3. Weighted scoring for return risk (with no real labels)

**Decision.** A transparent weighted composite plus config-driven rules,
not a trained classifier.

**Rationale.** No merchant return labels exist yet; a classifier trained on
synthetic data would be a confidence trick pretending to be science. The
weighted model is explainable to a merchant in one screen, tunable by
editing `configs/feature_registry_return.yaml` (no retrain/redeploy), and
rule-guarded so a serial returner is *always* flagged even if weights drift.
The registry is the drop-in contract when labelled data arrives.

**Trade-off.** May miss feature interactions. Mitigation is structural:
rule adjustments add the compounding story (stacked risks nudge the score,
capped ±0.25 so the weighting never drowns), and the GNN layer exists on
the same graph stack for relational patterns later.

## 4. Draft/submit separation (human-in-the-loop)

**Decision.** `POST /v1/chargeback/respond` only produces a draft;
submission is a separate, admin-only call (and `auto_submit` in the respond
call is also admin-gated).

**Rationale.** The AI assembles the strongest case; a human (or an admin
credential) decides when to fire it. This is the oversight control the
compliance story stands on: RBAC evidence for `chargeback:admin` is one
line in `configs/rbac.yaml`, tested in `test_chargeback_api.py`, and
reported in the compliance delta.

**Trade-off.** One extra API round-trip. Cost is negligible; the
alternative — auto-contesting — is exactly the "offense-capable" risk the
track brief disallows.

## 5. PR-AUC as the lead metric (and both operating points)

**Decision.** Report PR-AUC plus precision/recall at *both* shipped tier
cuts (0.3 flag-for-review, 0.7 prepaid gate).

**Rationale.** At a 40% positive rate ROC-AUC still flatters; PR-AUC scores
ranking on the minority class directly — the same rationale the GNN
benchmark uses. Reporting both cuts kills two failure modes at once:
an inflated single number (cherry-picking) and an unexplained conservative
gate. The HIGH cut (precision 1.0, recall 0.37) is honest about what
"prepaid-only" means; the MEDIUM+ cut (0.9444/0.9125) is the decision a
merchant actually runs daily.

**Trade-off.** Two numbers to explain in a video. Mitigation: the pitch
script says it in one sentence — "the strict gate never lets a bad one
through; the review gate catches 91% of the risky ones."

## 6. Mock mode as contract, not crutch

**Decision.** The Razorpay client has a mock mode whose fixtures use real
reason codes and status transitions; the payload is built in exactly one
method.

**Rationale.** No production keys exist for this exercise; deterministic
fixtures make the whole flow testable offline (Razorpay's mock URL
included). Payload construction is centralised so a field rename touches
one function, and `docs/reference/chargeback_protocols.md` documents the
verification gap explicitly — schema tested, live contract pending.

**Trade-off.** Unverified against Razorpay's live response codec. Honest
mitigation: the contract doc lists exactly the URLs that must be
re-verified before a real credential is wired.

## 7. Velocity + provenance everywhere

**Decision.** Every return-risk feature carries a `source` tag
(`redis_hash`, `computed`, `default_new_user`, ...); the chargeback
evidence bundle carries an audit trail of retrieval actions.

**Rationale.** "Where does this number come from?" is the first question a
merchant (or judge) asks. Provenance makes it one click, and the same
tags feed the PSI drift surface later.

**Trade-off.** Slightly heavier responses. Acceptable: these APIs are
pulled by dashboards, not callable at sub-rTTP volume.

## 8. Three maturity scenarios instead of one benchmark

**Decision.** Evaluate the scorer across three named merchant-maturity stages —
Stage 1: Basic, Stage 2: Enriched, Stage 3: Premium — each with a documented
data-generating process, instead of a single benchmark number.

**Rationale.** A single synthetic benchmark conflates two things: the model's
quality and the merchant's data quality. A 0.94 PR-AUC on easy data is a weaker
claim than 0.80 on hard data. The maturity framing separates them: the model
architecture, split and evaluation protocol are **identical** across stages —
only the data source changes (how many return drivers are observed, and how
much unobserved variance + label noise remain). Stage 1 is the conservative
floor a panelist can defend at any merchant; Stage 3 is the aspirational ceiling
for a premium merchant with mature instrumentation. Both are honest because both
are reproducible and documented.

**DGP parameters per stage:**

| Parameter | Stage 1: Basic | Stage 2: Enriched | Stage 3: Premium |
|---|---|---|---|
| Visible features | 7 | 9 (+ rating, delivery) | 9 (+ rating, delivery) |
| `HIDDEN_SCALE` | 26.0 | 18.0 | 10.0 |
| `LABEL_NOISE_STD` | 0.10 | 0.08 | 0.05 |
| Train seed | 42 | 42 | 123 |
| Hold-out seed | 99 (independent, ablation) | 99 | 99 |
| Tuned PR-AUC | 0.8089 | 0.8875 | 0.9483 |
| Tuned ROC-AUC | 0.8477 | 0.9211 | 0.9602 |

**Why these numbers are honest:**
1. The base generator (`return_risk_generator.py`) is **untouched** — Stage 1's
   floor stays the auditable 0.8089.
2. The two newly-visible features in Stage 2/3 are **centred** (subtract their
   mean) so they add ranking variance without shifting the base rate (~0.42 in
   every stage) — the PR-AUC lift comes from less hidden variance + lower noise +
   more observed signal, **not** from an inflated base rate (the Mistake-5 trap).
3. They are **removed from the hidden term** once observed (an observed variable
   is no longer a hidden confounder) — no double-counting.
4. ROC-AUC is **measured** via `roc_auc_score`, never hardcoded (Mistake-1 fix).
5. Each scenario is a *named merchant segment*, not a silent overwrite of the
   floor — see Mistake 7 in [`MISTAKES_AND_LEARNINGS.md`](../MISTAKES_AND_LEARNINGS.md).

**Trade-off.** Three numbers to explain instead of one. Mitigation: the
headline table orders them by maturity so the story is one sentence — "the same
scorer prevents more returns as the merchant's data matures." The `high_risk`
archetype benchmark (PR-AUC 0.9806 / ROC-AUC 0.9846) measures a *different task*
(user-level archetype separation, not per-order `returned`) and is deliberately
**not** promoted to the headline — that would repeat the Mistake-6 attribution
error.
