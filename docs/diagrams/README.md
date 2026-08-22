# Architecture Diagrams — Track 2

Mermaid sources live in this directory and render natively on GitHub.
For PNG/PDF exports:

```bash
# mermaid-cli (one-time): npx -y @mermaid-js/mermaid-cli -i system.mmd -o system.png
npx -y @mermaid-js/mermaid-cli -i docs/diagrams/system.mmd -o docs/diagrams/system.png
npx -y @mermaid-js/mermaid-cli -i docs/diagrams/chargeback_evidence_flow.mmd -o docs/diagrams/chargeback_evidence_flow.png
npx -y @mermaid-js/mermaid-cli -i docs/diagrams/return_risk_feature_breakdown.mmd -o docs/diagrams/return_risk_feature_breakdown.png
```

| Diagram | File | What it shows |
|---|---|---|
| System architecture | `system.mmd` | three endpoints → their engines → shared audit/Redis sinks |
| Chargeback evidence flow | `chargeback_evidence_flow.mmd` | webhook → verification → reconstruction → rebuttal → draft cache → admin-gated submit |
| Return-risk breakdown | `return_risk_feature_breakdown.mmd` | the exact 0.83 arithmetic: 7 contributions + capped rule adjustment |

ASCII fallbacks (render anywhere):

```
                +------------------+
                |   Merchant App   |
                +--------+---------+
         +--------------+---------------+
         v              v               v
+---------------+  +----------------+  +---------------------+
| /v1/score     |  | /v1/return/    |  | /v1/chargeback/     |
| fraud, live   |  | score          |  | respond              |
+-------+-------+  +-------+--------+  +---------+-----------+
        |                  |                     |
+-------+-------+  +-------+--------+  +---------+-----------+
| L1+L2+L3      |  | Feature Engine |  | Evidence Collector  |
| + ensemble    |  | Rules + Scorer |  | Rebuttal Builder    |
+-------+-------+  +-------+--------+  +---------+-----------+
        |                  |                     |
        v                  v                     v
+---------------+  +----------------+  +---------------------+
| ALLOW/REVIEW/ |  | tier + recs    |  | narrative + payload |
| BLOCK         |  | (HIGH/MED/LOW) |  | (draft -> admin-    |
+---------------+  +----------------+  |  gated submit)      |
                                        +---------------------+
```
