# Evaluator Guide — 10-Minute Walkthrough

**Start here.** PayShield is a return-risk scorer for Indian e-commerce (with
chargeback and fraud extensions on the same audit chain). This guide gets you
to the core evidence in 10 minutes. All reproduction commands are hermetic
(no Docker required) unless noted.

## Minute 1–2: The Business Case
- Open [`docs/COST_MODEL.md`](docs/COST_MODEL.md)
- See the gate sweep: a 10k-order fashion merchant saves **₹17.5 lakh/month**
  at the **0.50 review gate** (precision 0.677, recall 0.774 — the offline
  XGBoost operating point). The gate is config-driven per vertical; 0.50 is
  optimal for high-return verticals.

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

## The Enriched Feature Pipeline (future work, not a headline)

The Redis-enriched feature engine (`return_risk/feature_engine.py` + user/
merchant profiles) exists in the codebase and the live scorer runs on it, but
**the XGBoost model has not been recalibrated to enriched feature
distributions** — it was trained on the offline DGP's features. Two honest
caveats, both documented:

1. The enriched-path scorer (before the scope cut, hand-weighted) reached
   **0.9311 PR-AUC on the serial/fraud-archetype label** — a different target
   (user type, not per-order `returned`) and a different engine than the
   evaluated model. It is **not comparable** to 0.8067 and is **not** a
   headline number; see [`MISTAKES_AND_LEARNINGS.md`](MISTAKES_AND_LEARNINGS.md).
2. Applied today, the XGBoost model scores **0.82** on that archetype target
   and ~0.50 on the per-order `returned` label — because the enriched
   generator's `returned` outcome depends only on the user's latent rate (see
   `docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md`). Retraining on the enriched
   pipeline is "What I'd Do Next" #1.

## Quick Start (Hermetic, One Command)
```bash
python scripts/train_xgb_return_risk.py   # train + baseline comparison
python scripts/ablation_study.py          # feature evidence
python scripts/tune_xgb.py                # 144-combo hyperparameter search
```