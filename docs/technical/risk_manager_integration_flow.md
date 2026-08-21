# Risk-Manager Integration Flow — The Coherent Story

**Track 02 — Phase 7.** How PayShield's existing fraud scoring, the new
return-risk scorer and the chargeback evidence responder compose into one
story: proactive → reactive → remedial.

---

## The Three Acts

### Act 1 — Transaction Scoring (`POST /v1/score`, existing)
Fully **reactive**. L1 velocity/geo/Benford rules → L2 GNN conditional fusion
→ L3 async LLM investigation. Outcome `ALLOW / REVIEW / BLOCK`.

> Every ALLOW/REVIEW txn is a **future chargeback candidate**. Its audit log
> record is the raw material of Act 3 — nothing is re-analysed later.

### Act 2 — Return-Risk Scoring (`POST /v1/return/score`, new)
**Proactive**. Pre-dispatch / checkout: merchant answers *"will this order come
back?"* Features come from Redis (`return_risk:user:*`, `return_risk:merchant:*`)
and the order payload. Output: score + tier + **actionable recommendations**
(require prepaid / cap quantity / flag review).

### Act 3 — Chargeback Response (`POST /v1/chargeback/respond`, new)
**Remedial**. A `chargeback.created` webhook arrives weeks later. The evidence
responder is a **retrieval-and-format agent**:
1. resolve txn from the audit chain,
2. reassemble L1 rule snapshots + L2 graph score + L3 report,
3. overlay merchant delivery/customer evidence,
4. generate the narrative (existing Ollama infra, new template),
5. hand the merchant a draft (human approves) or submit directly (admin).

---

## Sequence Diagram

```text
Act 1 (t0)                                        Act 2 (t0 + days)          Act 3 (t0 + weeks)
User -> Razorpay: pay                             User -> Merchant: return   User -> Bank: "fraud!"
Razorpay -> PayShield /v1/score                   Merchant -> PayShield /v1/return/score   Bank -> Razorpay: chargeback
PayShield -> Redis: velocity/geo features          PayShield -> Redis: user profile          Razorpay -> PayShield webhook: chargeback.created
PayShield -> GNN: graph inference                  PayShield -> Redis: merchant baselines    PayShield -> Audit Log: evidence TXN001
PayShield -> Redis: write audit log               PayShield -> Merchant: score 0.73 HIGH     PayShield -> L1/L2/L3: pull stored results
PayShield -> Razorpay: ALLOW                      Merchant -> User: prepaid-only / review    PayShield -> LLM: draft narrative
                                                 **explicit callback for demo**              PayShield -> Merchant: rebuttal draft (REJECT) 
                                                                                             Merchant -> Razorpay: submit (human-in-loop)
```

## State Machine

```text
[ORDER_CREATED] --score---> return_risk:LOW      --> ACCEPT (dispatch)
                            return_risk:MEDIUM   --> FLAG_FOR_REVIEW
                            return_risk:HIGH     --> REQUIRE_PREPAID
                                                      |
[AUTHED_TXN] --/v1/score--> ALLOW | REVIEW | BLOCK
     | all three can later be disputed            |
[CHARGEBACK_OPEN] --deadline--> urgency 0..1      >- PARTIAL amount claimed?
     | complete evidence & deadline ok            |     \_ evidence < threshold -> ACCEPT
     v                                            |        evidence 50-80%    -> PARTIAL
[REBUTTAL_BUILT: ACCEPT|REJECT|PARTIAL]      [RESOLVED: REJECTED-PAID / ACCEPTED-REFUNDED]
     |
     +-- human review --> [SUBMITTED] --> [DISPUTE_CLOSED] --> audit trail finalized
```

## Data-flow map (what each stage reads/writes)

| Stage | Reads | Writes |
|---|---|---|
| /v1/score | Redis velocity lists, Benford hashes, GNN graph, Neo4j mirror | audit JSONL chain, layer1_audit mirror, graph DB, investigation task |
| /v1/return/score | `return_risk:user:{id}` hash, `return_risk:merchant:{id}:category`, order payload | nothing (read-only scorer) |
| /v1/chargeback/respond | audit JSONL chain, `benford:{merchant}` hash, `dfp:{device}` hash, L3 investigation row, merchant evidence (Razorpay/override) | rebuttal cache (redis), `CHARGEBACK_REBUTTAL` audit entries, secure-attachment URLs |

## Demo script outline (judge-told story)

1. **Live txn** — replay a burst from `demo-burst`; show ALLOW/REVIEW decisions
   and the audit entries (L1/L2/L3 evidence persisted at txn time).
2. **Return risk** — POST `/v1/return/score` for a seeded serial returner
   (U003 from `scripts/seed_redis.py`); project the feature wheel
   (`user_return_rate_30d` 0.35 etc.) and the `REQUIRE_PREPAID_ONLY` action.
3. **Chargeback** — fire a fake `chargeback.created` webhook for the ALLOWED
   txn; show the rebuttal JSON:
   - evidence completeness 0.92,
   - narrative with the exact L1/L2 numbers,
   - razorpay_payload preview rendered in the UI,
   - ask the judge: *"should we contest?"* — one click → submit.
4. **Honesty beat** — call `/v1/chargeback/respond` for a txn with no signup
   (fresh user: no L2, no L3) → completeness < threshold, response=PACCEPT
   with `warnings` — the model admits it cannot win this one.
