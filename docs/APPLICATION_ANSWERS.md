# Application Answers — Razorpay AI Buildathon, Track 02

All 12 questions, pre-written and copy-paste ready. Keep this file open in
a second window while filling the form — never type answers live.

---

## Personal (questions 1–6)

1. **Full name** — (fill in)
2. **College** — (fill in)
3. **Graduation year** — (fill in)
4. **In-person from September: yes / no** — (fill in)
5. **6 or 12 months: your pick** — (fill in)
6. **Resume file** — PDF, under 2 MB (fill in)

## 7. Your track

**02 — AI Risk Manager**

## 8. Project name

**PayShield: AI Risk Manager**

## 9. What it solves

> PayShield Track 2 solves two interconnected revenue-loss problems for
> Indian merchants:
>
> 1. **Chargeback evidence responder.** When a customer disputes a
>    transaction, merchants lose 2–4% of revenue to chargebacks while small
>    merchants lack the time or expertise to gather evidence (transaction
>    logs, device fingerprints, delivery proofs) and write professional
>    rebuttals. PayShield retrieves the L1/L2/L3 evidence PayShield already
>    captured at transaction time from a tamper-evident audit chain,
>    generates the narrative with the same LLM stack, and produces a
>    Razorpay-compatible contest payload — response time drops from hours of
>    manual work to a single API call, with evidence each piece traceable to
>    the moment the transaction was scored.
>
> 2. **Return-risk scorer.** Indian e-commerce return rates run 25–40% for
>    fashion, and merchants ship to customers who habitually return
>    ("serial returners") or commit return fraud (wardrobing, empty-box
>    returns). PayShield scores every order before dispatch using user
>    history, merchant patterns, category baselines and 8 config-driven
>    rules — producing explainable, merchant-actionable outcomes like
>    "require prepaid payment" or "flag for review" with a per-feature
>    breakdown (value · weight · contribution · source) in every response.
>
> Both systems reuse PayShield's L1 statistical filter, L2 graph neural
> network and L3 LLM investigation — defense-only, explainable and
> measured: PR-AUC 0.9806 on 10,000 synthetic held-out orders, both
> operating points reported (precision 1.0000 at the strict gate;
> 0.9444/0.9125 at the review gate), compliance checkers at PCI-DSS 90/100,
> RBI and EU AI Act passing — a layered risk manager, not a single detector.

## 10. GitHub repo URL

(fill in the public URL — verify it loads in incognito before submitting)

## 11. 5-min pitch video, unlisted

(fill in the unlisted YouTube URL — test in incognito AND on a phone)

## 12. What broke, and how you got out

> Four real breakages — each one taught a lesson about building risk
> systems, and each one is still covered by an automated test today.
>
> **1. The evidence collector lost every device it looked up.**
> PayShield's audit chain masks device IDs by design (PCI compliance), so
> the first draft of the chargeback evidence collector found only masked
> strings like "DEV-*****" and returned "no device evidence" for every
> transaction. A winnable dispute looked unwinnable.
> *Fix:* the collector now resolves masked IDs through the user→device
> Redis index (`ud:{user_id}`) that the pipeline maintains, falling back
> gracefully when even that is empty. Tested in
> `tests/unit/chargeback/test_evidence_collector.py`.
> *Lesson:* retrieval paths inherit masking rules silently — test against
> the *masked* reality, not the idealized record.
>
> **2. Every high-risk user scored MEDIUM, not HIGH.**
> With the published feature weights, a serial returner with a clean COD
> history summed to ~0.51 — under the 0.7 HIGH gate. Ranking was perfect
> (PR-AUC 0.98) but the tier boundary cut the wrong class.
> *Fix:* rather than re-weighting to make the demo look good, we made the
> already-existing rule mechanism first-class: fired rules produce a capped
> score adjustment (RULE_BOOST, ±0.25), the adjustment is derivable from
> the rules_triggered list in every response, and both operating points are
> reported honestly. The benchmark now shows precision 1.0000 at the strict
> gate and 0.9444/0.9125 at the review gate.
> *Lesson:* a score that's correct but mis-thresholded is not correct — and
> "the model is right, the demo is wrong" is a thinking error, not a
> triumph.
>
> **3. A Decimal transaction amount turned a 422 into a 500.**
> Adding `amount: Decimal` with a `gt=0` bound surfaced a latent bug in the
> validation handler: FastAPI's pydantic error payload carried a plain
> `Decimal` in the constraint context, which the existing JSON error
> writer couldn't serialize. A malformed checkout request crashed the API.
> *Fix:* the validation handler now sanitizes error details with FastAPI's
> own encoder, so constraint metadata serializes for every schema, not just
> float-based ones. Covered in
> `tests/integration/test_return_risk_api.py`.
> *Lesson:* new schema types can expose old handlers; serialize boundaries
> with the framework's encoder, not a hand-rolled writer.
>
> **4. The benchmark's train/test split leaked the future.**
> The first benchmark sliced the generated dataset in order — which split
> *users* between train and test, letting the scorer see each test user's
> whole history. Its "PR-AUC 0.99" was a leakage artifact.
> *Fix:* chronological per-user hold-out: each user's first 80% of orders
> seed the profile window, the remaining 20% are scored. Also wired
> user-side velocity windows so scores never use returns after the order
> date. PR-AUC 0.9806 on this split is real; the leakage number is gone.
> *Lesson:* a metric is only as trustworthy as the split beneath it.

---

## Supporting documents checklist

- [ ] Resume PDF < 2 MB, typo-free
- [ ] Repo public — verified in incognito
- [ ] Video unlisted — verified in incognito + on phone
- [ ] Project name identical in repo, README, video, form ("PayShield: AI Risk Manager")
- [ ] Track number correct: 02 — AI Risk Manager
