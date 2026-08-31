# Track 2 Architecture — Return-Risk

> **Scope:** Track 2 is the **return-risk** surface. Fraud (`engine/`, `ml/`)
> and chargeback (`chargeback/`) extensions exist in the repo as earlier
> platform work but are **out of scope** for this track — their routes remain
> mounted but unmeasured, and every number here covers return-risk only.

## The pre-shipping lifecycle

```
            ┌────────────────────────────┐
            │  Razorpay order.paid /      │
            │  POST /v1/return/score      │
            └───────────┬────────────────┘
                        ▼
            ┌────────────────────────────┐
            │  ReturnRiskFeatureEngine   │   Redis: user history, merchant
            │  (user + merchant + txn)   │   baselines, category zsets
            └───────────┬────────────────┘
                        ▼
            ┌────────────────────────────┐
            │  RulesEngine (YAML, reload)│   9 config-driven rules incl.
            │  evaluate(features)        │   abuse-ring sentinel R-RULE-09
            └───────────┬────────────────┘
                        ▼
            ┌────────────────────────────┐
            │  XGBoost primary           │   live-features model (PR-AUC 0.8139)
            │  fallback: weighted scorer │   on the 7-feature schema, clamped
            └───────────┬────────────────┘   to the training envelope
                        ▼
            ┌────────────────────────────┐
            │  Tier + recommendations    │   LOW → ACCEPT · MEDIUM → review
            │  + Model Waterfall (explain)│  HIGH → REQUIRE_PREPAID (defense-only)
            └───────────┬────────────────┘
                        ▼
            ┌────────────────────────────┐
            │  Audit chain (every decision) + human-review queue (MEDIUM)
            └────────────────────────────┘
```

Extensions (out of scope): a fraud path (`POST /v1/score`, L1 velocity/geo +
conditional L2 GNN + ensemble) and a chargeback responder
(`POST /v1/chargeback/respond`, evidence reconstruction + admin-gated
submit) — see the README's Repository Scope for the honest accounting.

## Shared sinks (one source of truth)

| Sink | Return-risk consumers |
|---|---|
| `store/audit_logs/` — tamper-evident JSONL chain | every `RETURN_RISK_SCORED` decision, webhook event log, human-review queue source |
| Redis `return_risk:*` | feature engine (profiles, return velocity zsets, merchant baselines, category zsets) |
| Redis `address:{hash}:users` | abuse-ring sentinel (PII-free address-hash sets) |
| `configs/{feature_registry_return.yaml, return_risk_rules.yaml, rbac.yaml, config.yaml}` | weights, rules, permissions, thresholds — all code-free tuning |

## Request/response lifecycle

**Return risk** (read-only hot path): score request → concurrent user/merchant
extraction from Redis → transaction features (ratio clamped to the model's
`[0.15, 4.0]` envelope) → rules (severity-ordered) → XGBoost prediction
(hand-weighted fallback) → abuse-ring override → tier + recommendations →
response with per-feature contributions, `engine`, `model_path` and the model
feature vector; profile refreshed in background. `POST /v1/return/explain`
replays the same path and returns the Model Waterfall attribution.

**Webhooks** (signed, HMAC-verified): `order.paid` → score before dispatch;
`refund.processed` → ground-truth label for retraining. Unverified payloads
are rejected with `400` before any work.

## Distinctive design choices (summary — full rationale in docs/DESIGN_DECISIONS.md)

1. **Defense-only tiers** — MEDIUM → review, HIGH → prepaid; no autonomous
   blocks, including the abuse-ring sentinel (score floor, never a block).
2. **XGBoost primary, trained on the live feature pipeline** — the live scorer
   runs `models/return_risk_xgb_live.json` (test PR-AUC 0.8139), trained on the
   exact 7-feature vector the API computes, clamped to the training envelope so
   it is never out-of-distribution. The offline DGP models remain the evaluated
   data-maturity evidence (0.7991 → 0.9497).
3. **Provenance on every feature** — `value · weight · contribution · source`
   per feature, so any score is explainable down to the penny.
4. **Reconstruct over re-analyse** — the audit chain is the single source of
   truth (chargeback extension design; keep for the return-risk label loop).
5. **Honest numbers** — every headline reproduces from `--full-verify`;
   confidence and evidence degrade loudly when data is thin.
