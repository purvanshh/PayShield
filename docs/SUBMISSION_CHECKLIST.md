# Submission Checklist — PayShield: AI Risk Manager

The final gate before hitting submit. Anything marked **repo** is done and
verifiable in the tree; anything marked **/manual/** is yours to do
(external links, form, recordings). Work top to bottom — never submit with
a manual item unchecked.

## Code & repo

- [x] **repo** — 589 tests pass (`pytest tests/ -q`), hermetic
- [x] **repo** — Track 2 logic strict-typed (`mypy chargeback/ return_risk/ --strict`)
- [x] **repo** — ruff clean on track-2 code (repo-wide B008 convention is
      pre-existing and matches `api/routes/score.py`)
- [x] **repo** — bandit 0 findings on `chargeback/ return_risk/`
- [x] **repo** — coverage 76.4% suite · 91.1% track-2 modules
      (`reports/quality_gate_track2.md`)
- [x] **repo** — compliance checkers pass in the compose env
      (`COMPLIANCE_DELTA_TRACK2.md`: PCI 90/100 · RBI 83/100 passing ·
      EU 100/100)
- [x] **repo** — README leads with the return-risk scorer hero narrative;
      fraud + chargeback demoted to Platform Extensions
- [x] **repo** — cost model: `docs/cost_model/calculator.py` reproduces the
      headline ₹27,45,990/month savings (54.6%); unit-pinned
- [x] **repo** — Razorpay integration: `integrations/razorpay_adapter.py`,
      signed webhook handler + test-mode client; 11 tests
- [x] **repo** — A/B simulation: `scripts/simulate_ab_test.py` (Welch t-test,
      promote/keep recommendation)
- [x] **repo** — graceful-failure demo: `scripts/demo_graceful_failure.py`
      (3 scenarios against the real scorer)
- [x] **repo** — agents slimmed to the 4 live paths; dev-only agents archived
      under `agents/archived/` with status + re-enable notes
- [x] **repo** — stories: `docs/THREE_HARD_BUGS.md`
- [x] **repo** — tag `v1.2.0-track2` exists (local)
- [ ] **/manual/** — repo public on GitHub; `git push origin feature/track2-risk-manager`
- [ ] **/manual/** — push the tag (`git push origin v1.2.0-track2`)
- [ ] **/manual/** — `truffleHog .` / `git-secrets --scan` on the pushed ref
- [ ] **/manual/** — fresh clone → `docker compose -f docker/docker-compose.yml up`
      → health OK → `python scripts/seed_demo_data.py` → six scenarios verified

## Video

- [ ] **/manual/** — 5:00 main video: unlisted YouTube, chapters at 0:20/0:50/
      1:40/2:20/3:10/3:40/4:00/4:30 (structure: `docs/video_production.md`)
- [ ] **/manual/** — link tested in incognito **and** on a phone
- [ ] **/manual/** — optional 2:00 deep dive (`docs/DEEP_DIVE_VIDEO.md`)
      linked in README under "Deep dive"
- [ ] **/manual/** — backup take on disk until submission is confirmed

## Form (answers in `docs/APPLICATION_ANSWERS.md`)

- [ ] **/manual/** — personal fields filled in the doc first, then copied
- [ ] **/manual/** — track "02 — AI Risk Manager"; project name identical
      everywhere
- [ ] **/manual/** — repo URL public-verified; video URL unlisted-verified
- [ ] **/manual/** — resume PDF < 2 MB uploaded
- [ ] **/manual/** — submit early, not at the deadline; screenshot the
      confirmation page

## What is frozen

Code is final. No new features after this checklist is started; a bug that
surfaces now gets a `fix:` commit only, rebased on this branch and pushed —
never a silent re-spin of the demo data.
