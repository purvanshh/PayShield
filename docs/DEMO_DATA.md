# Track 2 Demo Data — Scenarios & Verified Outputs

`python scripts/seed_demo_data.py` seeds Redis + the audit chain with six
curated scenarios. The outputs below were **verified in-process against the
exact seed** (2026-08-22, hermetic run — no live services needed): the
return-risk numbers come from the real scorer, the chargeback numbers from
the real collector+builder, the L1 numbers from the real statistical filter.

## Scenario 1 · TXN_CLEAN_001 — the clean transaction

- Seeded: `U_CLEAN_001` profile (20 orders / 2 returns), `DEV_CLEAN_001`
  device index (210 days of history), 3 velocity events in the last hour.
- Verified L1: `decision=ALLOW`, `rules=[]` (velocity/geo within bounds,
  Mumbai → Mumbai, Benford distribution normal).
- Demo line: *"every rule passes — the pipeline runs in sub-milliseconds
  and the transaction goes through."*

## Scenario 2 · TXN_SUSPICIOUS_001 — the burst

- Seeded: `U_FRAUD_001` (80% return rate), `DEV_SHARED_001` shared by 3
  ring users, 12 × ₹95,000 velocity events in 5 minutes, Mumbai→Delhi jump.
- Verified L1: `decision=BLOCK`, `rules=['V-RULE-04', 'V-RULE-03', 'G-RULE-01']`
  (device flood + amount 5× median + impossible geo velocity).
- Demo line: *"rules explain *what* broke; the graph layer (not shown here)
  would explain *who else* shares that device."*

## Scenario 3 · ORD_SERIAL_001 — serial returner

- Seeded: `U_SERIAL_001` (15 orders / 10 returns = 66%),
  3 returns in the last 7 days, 3/8 COD refusals, fashion merchant 30%.
- Verified score: **0.8275 · HIGH**
  - contributions: rate 0.165 + serial 0.20 + merchant 0.045 + category 0.045
    + amount 0.055 + cod-refusal 0.0375 + velocity 0.03 = 0.5775
  - + rule adjustment 0.25 (capped: R-01+R-02+R-03+R-04 = 0.45 → cap 0.25)
  - rules fired: `R-RULE-01, R-RULE-02, R-RULE-03, R-RULE-04, R-RULE-06`
  - recommendations: prepaid-only + manual review + signature on delivery
  - confidence 1.0 (full history, no defaults)
- Demo line: *"the merchant sees 0.83 with five auditable nudges — and the
  exact arithmetic in the feature breakdown."*

## Scenario 4 · ORD_HONEST_001 — honest customer

- Seeded: `U_HONEST_001` (25 orders / 2 returns = 4%), electronics merchant.
- Verified score: **0.096 · LOW** (only `R-RULE-08` ACCEPT rule fires)
  - note `txn_amount_risk`: 12000/10000 capped at 1.0 → 0.10 contribution;
    the rule stack still keeps the total LOW.
- Demo line: *"high-value electronics with a clean profile just clears.
  No false-positive drama."*

## Scenario 5 · CB_WINNABLE_001 — winnable dispute

- Seeded audit entry for `TXN_CLEAN_001` (allowed, zero rules, device on
  file), Visa 10.4, deadline 2026-09-20.
- Verified response: **REJECT · confidence 1.0 · completeness 1.0**
  - evidence slots: `amount`, `summary`, `detailed_reason`, `billing_proof`
  - audit trail: `L1_EVIDENCE_COLLECTED → REBUTTAL_ASSEMBLED`
  - narrative: deterministic fallback (LLM optional) — same facts, honest
    wording
- Demo line: *"the rebuttal is assembled from evidence gathered at
  transaction time — we never re-analyse, we retrieve."*

## Scenario 6 · CB_WEAK_001 — the honest loss

- Seeded audit entry for `TXN_NEW_001` (brand-new user, no device record).
- Verified response: **PARTIAL · confidence 0.68 · completeness 0.68**
  - `graph_evidence=None`, `investigation_report=None`
  - warnings: graph evidence incomplete + LLM report unavailable
- Demo line: *"this is the case we can't win on evidence — the system says
  so instead of pretending. That's the honest-AI beat."*

## Seeded keys (for reference)

```
return_risk:user:*            # U_CLEAN_001, U_FRAUD_001, U_SERIAL_001,
                              # U_HONEST_001 profiles
return_risk:user:*:returns    # velocity zsets (fraud + serial users)
return_risk:merchant:*        # M_FASHION_001 (0.30), M_ELECTRONICS_001 (0.12)
return_risk:merchant:*:category  # category baselines incl. fashion 0.32 baseline
dfp:*                         # DEV_CLEAN_001, DEV_SHARED_001 device index
ud:DEV_SHARED_001             # shared-device membership (ring users)
velocity:user:*               # clean (3 events) + suspicious (12 × ₹95k)
benford:M_FASHION_001         # normal amount distribution
store/audit_logs/             # SCORE_DECISION entries for TNX_CLEAN_001,
                              # TXN_NEW_001 (read by the responder)
```
