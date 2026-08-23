# Panel-Day Execution Checklist

Everything under *manual* is yours to do on the day — nothing here
requires a code change (the codebase is frozen, `docs/FREEZE.md`).

## The night before

- [ ] 8 hours of sleep (this is preparation, not procrastination)
- [ ] Internet + camera + mic tested; headset with mute switch
- [ ] IDE open to `docs/PANEL_PREP.md` side-window, terminal split
- [ ] Demo stack up: `make up` → `/health` green → `python scripts/seed_demo_data.py`
- [ ] `reports/quality_gate_track2.md` + `models/return_risk_benchmark_results.json`
      open in a spare tab
- [ ] Architecture: `docs/diagrams/system.mmd` tab (or paper whiteboard)
- [ ] Water + notepad

## The day: opening (2 min)

"Hi, I'm Purvansh. PayShield Track 2 is an AI Risk Manager — it extends my
fraud detection system with two new defence layers: a chargeback evidence
responder (remedial) and a return-risk scorer (proactive). Let me draw the
three acts, then show you the code and the honest numbers."

## The day: segments

1. **Architecture (5 min)** — three boxes, one audit chain underneath;
   say "read-only collector" and "confidence is diagnostic" out loud.
2. **Live evidence (3 min)** — the hermetic gates:
   `python -m pytest tests/ -q | tail -1`,
   `mypy chargeback return_risk --strict --follow-imports=skip` —
   plus the grand pipeline test (one file, all three systems).
3. **Metrics (3 min)** — `cat models/return_risk_benchmark_results.json`
   reading PR-AUC first, then both operating points, then the honest
   caveat (HIGH gate under-catches by design).
4. **Failure demo (2 min)** — break the LLM: with none running the
   rebuttal still builds (fallback narrative); show the 2.0s guard by
   pointing at the chaos test.
5. **Close (2 min)** — one-week wishlist (real data, cross-merchant graph,
   outcome webhooks) + repo/video links.

## If stumped

Never fill a gap with an invented number. Say: "That's a question I
haven't measured yet — my approach would be X, and I'd verify it with Y
before shipping." Then move on. One honest "don't know" per panel beats
one fabricated answer.

## Post-panel (within 24h)

- [ ] Thank-you email: repo link, video link, and the one item you
      couldn't answer fully with your follow-up thinking
- [ ] Save the confirmation/recording artifacts
- [ ] Keep the repo and stack in the frozen state until a decision
