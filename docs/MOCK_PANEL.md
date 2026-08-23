# Mock Panel — Full Dress Rehearsal

Simulate the real panel with a second person (friend/mentor/agent — the
format is identical). 45 minutes; record it and score yourself on the
feedback sheet below.

## Format (45:00)

| Window | Segment | What the mock panel does |
|---|---|---|
| 0–5 | Intro | You pitch (2 min); panel asks two clarifying questions |
| 5–15 | Architecture | You draw the three-act flow; panel interrupts with: "Why Redis and not Postgres for features?" · "LLM down?" · "two chargebacks for the same txn?" |
| 15–25 | Code review | Panel picks: `chargeback/rebuttal_builder.py::_determine_response_type`, `return_risk/scorer.py::_compute_score`, `tests/integration/test_chargeback_flow.py` |
| 25–35 | Domain | RBI timelines · NPCI DRF vs Visa · false-positive cost · scaling to Razorpay volume |
| 35–45 | Behavioural | "A trade-off you regret" · "disagreeing with a teammate" · "why Razorpay / why this track" |

## Hard questions to plan for (beyond PANEL_PREP)

- "Who owns the mask function — writer or reader?" (answer: writer masks
  before hashing; the reader resolves masked ids via the user→device index.)
- "Why is confidence 1.00 for the winnable case, and is that overconfident?"
  (answer: completeness is asserted by construction; confidence is
  evidence-coverage, not win-probability — say the words.)
- "Your chargeback latency number?" (answer: the pipeline number from
  `reports/perf_optimization.json` is 0.05–0.12 ms in-process; API-visible
  latency is reported `latency_ms` per request; live-stack load numbers
  are the harness that still needs a run.)
- "Where will real return-fraud data come from?" (answer: Razorpay
  sandbox + merchant opt-in; the registry is the model contract.)

## Feedback sheet (panel fills, you record)

| Dimension | 1–10 |
|---|---|
| Clarity of explanations | |
| Depth of technical knowledge | |
| Honesty about unmeasured claims | |
| Confidence and poise | |
| Recovery from a hard/no answer | |

Three action items from this rehearsal go into the panel-day checklist
before you stop recording.

## Rehearsal rules

1. No script reading — `docs/PANEL_PREP.md` is a map, not a teleprompter.
2. Every numeric claim must be followed by its source file, aloud.
3. One unanswerable question per session is a success — practise the
   "here's my approach" frame.
4. Record, rewatch at 1.5x, note fillers ("um", "basically", "you know").
