# Track 2 Architecture

## The three-act risk lifecycle

```
                    ┌────────────────────────────┐
                    │      Merchant App          │
                    └───────────┬────────────────┘
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐
  │ POST /v1/score  │  │ POST /v1/return │  │ POST /v1/chargeback/ │
  │ (fraud, live)   │  │ /score          │  │ respond              │
  └────────┬────────┘  └────────┬────────┘  └──────────┬───────────┘
           │                    │                      │
  ┌────────▼────────┐  ┌────────▼────────┐  ┌──────────▼───────────┐
  │ L1 velocity/geo │  │ ReturnRisk      │  │ ChargebackEvidence   │
  │ L2 GNN (cond.)  │  │ FeatureEngine   │  │ Collector (audit    │
  │ L3 LLM (async)  │  │  (Redis profile)│  │  chain re-read)     │
  │ Ensemble fusion │  └────────┬────────┘  └──────────┬───────────┘
  └────────┬────────┘           │                      │
           │           ┌────────▼────────┐  ┌──────────▼───────────┐
           │           │ RulesEngine     │  │ RebuttalBuilder      │
           │           │ (YAML, reload)  │  │ (type/narrative/     │
           │           └────────┬────────┘  │  Razorpay payload)   │
           │                    │           └──────────┬───────────┘
           │           ┌────────▼────────┐              │
           │           │ Weighted Scorer │  ┌──────────▼───────────┐
           │           │ (breakdown)     │  │ NarrativeGenerator   │
           │           └────────┬────────┘  │ (LLM or fallback)    │
           │                    │           └──────────┬───────────┘
           │           ┌────────▼────────┐              │
           │           │ Tier + recs     │  ┌──────────▼───────────┐
           └──────────►└─────────────────┘  │ RazorpayClient       │
                                            │ (mock / real)        │
                                            └──────────┬───────────┘
                                                       ▼
                                           ┌───────────────────────┐
                                           │ human review → submit │
                                           │ (chargeback:admin)    │
                                           └───────────────────────┘
```

## Shared sinks (one source of truth)

| Sink | Track 2 consumers |
|---|---|
| `store/audit_logs/` — tamper-evident JSONL chain | evidence collector (point-in-time reconstruction), webhook event log, justification for RBI controls |
| Redis `return_risk:*` | feature engine (profiles, velocity zsets, merchant baselines, category zsets) |
| Redis `velocity:user:*`, `dfp:*`, `ud:*`, `benford:*` | L1 features + evidence collector device/merchant evidence |
| Redis `chargeback:rebuttal:{dispute_id}` | draft cache (TTL 30d) + `chargeback:payment_txn:{payment_id}` for webhook auto-assembly |
| `configs/{feature_registry_return.yaml, return_risk_rules.yaml, rbac.yaml, config.yaml}` | weights, rules, permissions, thresholds — all code-free tuning |

## Request/response lifecycle

**Return risk** (read-only hot path): score request → concurrent
user/merchant extraction → txn features → rules (severity-ordered) →
weighted composite + capped rule adjustment → tier + recommendations →
response with per-feature contributions; profile refreshed in background.

**Chargeback** (remedial path): webhook (HMAC-verified) or manual call →
txn resolved from audit chain → L1 snapshot + device/merchant evidence →
completeness score → rule-based response type (ACCEPT/REJECT/PARTIAL) →
narrative (LLM with deterministic fallback) → Razorpay payload cached →
draft returned; only `chargeback:admin` can submit.

## Distinctive design choices (summary — full rationale in docs/DESIGN_DECISIONS.md)

1. Reconstruction over re-analysis — rebuttals use transaction-time
   knowledge, never hindsight (evidence collector is read-only).
2. Rules for the binary verdict — chargeback response is a legal claim,
   not a probability; explainability wins.
3. Weighted scoring for return risk — no labels yet; explainable,
   merchant-tunable, rule-guarded.
4. Draft/submit separation — human-in-the-loop by construction.
5. Honest numbers — both operating points documented; confidence and
   completeness degrade loudly when evidence is thin.
