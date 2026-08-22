# Recording Setup & Checklist

Everything needed to shoot the pitch video cleanly (see `docs/DEMO_SCRIPT.md`
for the 6-scene script, `docs/video_production.md` for the 5:00 structure and
editing pass).

## Environment (before any recording)

- **Stack:** `make up` — api, worker, redis, ollama, dashboard healthy
  (`check /health`).
- **Demo data:** `python scripts/seed_demo_data.py` (also re-runnable —
  idempotent overwrites).
- **Terminal:** iTerm2 (or Terminal.app), font 18pt+, dark background,
  half-screen width, no hard-wrapped lines (fixed terminal width, or
  `export COLUMNS=180`).
- **Browser tab:** Swagger UI at `http://localhost:8000/docs` — zoom 125%.
- **Scratch file:** `demo-commands.sh` with every curl pre-typed — never
  type live during the recording.
- **Notifications off:** Slack/Discord/email/phone silenced; screen-capture
  permissions clean; desktop wallpaper neutral.

## Per-take checklist

- [ ] Services healthy (`curl -s localhost:8000/health`)
- [ ] Demo data seeded (run the seeder immediately before recording)
- [ ] All six scenes rehearsed at least once end to end
- [ ] Font/zoom verified on the *recording* (check a freeze-frame)
- [ ] Microphone loudness ~ −12 dBFS; no keyboard noise (use screen
      recording with mic-off for the clickety parts)
- [ ] Timer started — you have a 0:45 checkpoint per scene
- [ ] No terminal history with secrets (use fresh shell; API key shown in
      commands is the dev key only)

## Common mistakes (and fixes)

| Mistake | Fix |
|---|---|
| Typing commands live | Paste from the scratch file |
| Numbers without context | Always say "this is from the benchmark run on 10k synthetic orders" before quoting |
| Scrolling through the repo | Open only the 3 files you narrate |
| Unreadable output | `python -m json.tool` every JSON response before recording |
| Skipping the failure scene | It is *the* honesty beat — never cut it |
| Mumbling footnotes | Rehearse Scene 5 twice — it is also the pitch reel moment |

## What to have on screen only

1. Terminal (API calls) — 60% of airtime
2. Swagger UI (endpoint list, schemas) — 15%
3. `docs/DEMO_SCRIPT.md` tab with current scene highlighted — 10%
4. `models/return_risk_benchmark_results.json` (metrics scene) — 10%
5. Editor with `return_risk/scorer.py` or `chargeback/rebuttal_builder.py`
   open during the architecture beat — 5%

## Output requirements

- 1920×1080, 30 fps, H.264/AAC (OBS "1080p30" preset)
- Unlisted YouTube link — verify in an incognito browser *before* the
  submission form
- Keep a second full take as backup on local disk (never delete takes
  until submission is confirmed)
