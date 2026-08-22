# Video Production Guide — 5:00 Structure & Editing

Target: exactly 5:00. Scene-by-scene table with overlays and chapter
markers. Record twice; finalize the clean take.

## Structure (5:00)

| Time | Section | Show | Overlay on screen | Narrator cue |
|---|---|---|---|---|
| 0:00–0:20 | Hook | Problem statement | "18B UPI txns/mo · 2–4% revenue lost" | personal motivation line |
| 0:20–0:50 | Architecture | `docs/diagrams/system.excalidraw.png` or mermaid render; editor with `rebuttal_builder.py` | three-actor strip: REACTIVE → PROACTIVE → REMEDIAL | one sentence per act |
| 0:50–1:40 | Transaction scoring | `POST /v1/score` (TXN_CLEAN_001) | decision + latency banner | L1 rules → conditional L2 → async L3, in that order |
| 1:40–2:20 | Return risk | `POST /v1/return/score` (ORD_SERIAL_001) | "0.83 · HIGH · 5 rules" | point at feature_breakdown while talking |
| 2:20–3:10 | Chargeback response | `POST /v1/chargeback/respond` (CB_WINNABLE_001) | "REJECT · conf 1.0 · completeness 1.0" | evidence → narrative → draft only |
| 3:10–3:40 | Metrics | `python scripts/benchmark_return_risk.py` tail | PR-AUC 0.9806 / P 0.9444 / R 0.9125 | chronological hold-out, both operating points |
| 3:40–4:00 | Failure recovery | CB_WEAK_001 + `TXN_NONEXISTENT` 404 | "conservative PARTIAL · warnings" | "the honest-AI beat" |
| 4:00–4:30 | Code quality | `pytest tests/ -q` tail + coverage line | "530+ tests · ruff clean" | hermetic tests, no services |
| 4:30–5:00 | Closing | repo + repo URL | v1.2.0-track2 | key takeaways |

## Overlay style

- One accent color; 3 lines max; hide within 4 s of its section ending.
- Numbers only from the measured benchmarks (`models/return_risk_benchmark_results.json`),
  never the verbal "~" estimates.

## Post-production pass

1. Trim: cut every pause > 2 s; no external music during technical
   sections (intro/outro only, −18 dB).
2. Overlays keyed to the table above.
3. Chapters at 0:00 / 0:20 / 0:50 / 1:40 / 2:20 / 3:10 / 3:40 / 4:00 / 4:30.
4. Loudness: dialogue −16 LUFS ±1; speech processed with a light EQ + 2:1
   compressor; no de-esser overdrive.
5. Export: 1920×1080, 30 fps, H.264 8 Mbps, AAC 192 kbps stereo.
6. Upload as **unlisted**; verify link in incognito; keep take #2 on disk
   until submission confirmed.

## Backup plan if the stack misbehaves

- Redis down → run demo with `--redis`-less benchmarks only? No: fix the
  stack first (compose restart), never record a degraded demo.
- Ollama down → the narrative falls back to the deterministic generator
  (by design) — say so on camera instead of hiding it.
- Port clash → confirm `make up` health before rolling; document the fix
  silently.
