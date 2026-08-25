# Evaluator Guide — 10-Minute Walkthrough

**Start here.** PayShield is a return-risk scorer for Indian e-commerce (with
chargeback and fraud extensions on the same audit chain). This guide gets you
to the core evidence in 10 minutes. All reproduction commands are hermetic
(no Docker required) unless noted.

## Minute 1–2: The Business Case
- Open [`docs/COST_MODEL.md`](docs/COST_MODEL.md)
- See the 0.30 → 0.50 gate sweep: a high-return merchant flips from losing
  **−₹9.8 cr/month** to saving **+₹0.81 cr/month**. The headline: a 10k-order
  fashion merchant saves **₹20.9 lakh/month**.

## Minute 3–4: The Model
- Open [`scripts/train_xgb_return_risk.py`](scripts/train_xgb_return_risk.py)
- Run: `python scripts/train_xgb_return_risk.py` (~20s, hermetic)
- See: **XGBoost PR-AUC 0.8067** vs. the best naive baseline 0.6991 (**+0.11 lift**)
  and vs. the hand-weighted scorer 0.7896. The model learns from a deliberately
  **non-circular** synthetic DGP (visible features + hidden confounders).

## Minute 5–6: The Evidence
- Open [`scripts/ablation_study.py`](scripts/ablation_study.py)
- Run: `python scripts/ablation_study.py` (~60s, hermetic)
- See: leave-one-feature-out retraining — **every feature shows a positive,
  unique PR-AUC drop** against hidden confounders; removing **both** return-rate
  features at once costs **−10.5%**, the largest signal block.

## Minute 7–8: The System
- Open [`scripts/verify_live_stack.py`](scripts/verify_live_stack.py)
- Run (needs Docker): `docker compose -f docker/docker-compose.yml up` then
  `python scripts/seed_demo_data.py` then `python scripts/verify_live_stack.py`
- See: the ten curated scenarios (serial returner → HIGH, honest → LOW,
  chargeback response, webhook signatures, drift) against real Redis.

## Minute 9–10: The Limitations
- Open [`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md)
- See: honest accounting of what broke — a fabricated "AUC > 0.92", a broken
  PSI drift estimator (43.4 → 3.86), a demo that failed in front of a friend —
  and how each was fixed. The README's Appendix C holds the full 24-entry
  register; [`MISTAKES_AND_LEARNINGS.md`](MISTAKES_AND_LEARNINGS.md) distills
  the five that changed how the project is built.

## Beyond 10 Minutes
- Full architecture: [`docs/TRACK2_ARCHITECTURE.md`](docs/TRACK2_ARCHITECTURE.md)
- Razorpay integration: [`docs/RAZORPAY_INTEGRATION.md`](docs/RAZORPAY_INTEGRATION.md)
- Compliance: [`COMPLIANCE_DELTA.md`](COMPLIANCE_DELTA.md)
- Business impact: [`BUSINESS_IMPACT.md`](BUSINESS_IMPACT.md)

## Why We Don't Report XGBoost on Redis-Enriched Features

The live Redis-backed system (PR-AUC 0.9311) uses the **hand-weighted scorer**
with enriched features. We have not isolated **XGBoost on Redis-enriched
features** as a separate benchmark because:

1. **Production reality:** the live system is a hybrid — XGBoost primary,
   hand-weighted fallback, both consuming the same Redis-enriched feature
   pipeline. Isolating XGBoost would require disabling the fallback, which
   never happens in production.
2. **Engineering priority:** the 0.8067 → 0.9311 gap (PR-AUC **+0.12**) proves
   feature enrichment matters more than model choice. "What I'd Do Next" #1 is
   an A/B test of XGBoost vs. hand-weighted on live enriched data.
3. **Honest scope:** the prototype was built in five days. Isolating every
   pipeline permutation is future work, not current evidence.

The honest answer: **we don't know XGBoost-on-enriched PR-AUC yet.** The
harness to measure it is built. We need a merchant partner to run it. That is
scope discipline — a virtue in engineering.

## Quick Start (Hermetic, One Command)
```bash
python scripts/train_xgb_return_risk.py   # train + baseline comparison
python scripts/ablation_study.py          # feature evidence
python scripts/tune_xgb.py                # 144-combo hyperparameter search
```