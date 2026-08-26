# Synthetic Chargeback Dataset — v1 Report

**Generated with `data.synthetic.chargeback_generator.ChargebackSyntheticGenerator`
(seed 42, 100 transactions, 15% chargeback rate).** Committed fixture:
`data/synthetic/chargeback_dataset_v1.json` — each transaction carries the
point-in-time L1/L2/L3 evidence the pipeline produced at scoring time, and
each chargeback inherits its transaction's record plus dispute metadata.

## Composition

| Metric | Value |
|---|---|
| Transactions (all ALLOWED by PayShield) | 100 |
| Chargebacks | 12 (12.0%) |
| With L2 graph evidence | 56/100 |
| With L3 LLM investigation (LLM stack since removed) | 34/100 |

## Chargebacks by network

```
UPI          5
VISA         3
MASTERCARD   3
RUPAY        1
```

## Reason code distribution

```
12.4  3 | 13.3  2 | 13.1  1 | 10.5  1 | 10.4  1
12.2  1 | 13.2  1 | FRAUD 1 | 12.1  1
```

Dispute classes: processing 5, service 4, fraud 3.

## Evidence completeness characteristics

- Fraud disputes (10.4/10.5/FRAUD) dominate the high-bundle cases (~80%
  completeness) because L1 velocity/geo snapshots exist for every allowed
  transaction and the audit chain keeps them for 12 months.
- Service disputes (13.x) are the honest-completeness battleground: a
  rebuttal without delivery proof scores below the 0.6 auto-submit
  threshold — that is the designed behavior, not a bug.

## Why every transaction is ALLOWED

A BLOCKED transaction never settles, cannot trigger a payout dispute,
and therefore cannot produce a chargeback. The dataset deliberately only
contains ALLOWED transactions — matching reality.
