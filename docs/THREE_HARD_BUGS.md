# Three Hard Bugs, Told as Stories

The build asked: *what broke, and how you got out.* The full register has
34 entries (README Appendix B); here are the three that hurt the most —
each with the root cause, the debugging trail, and what it permanently
changed about how I build.

---

## Bug 1 — "My drift detector was working." It wasn't. (PSI 43.4 → 3.86)

**Symptom.** The drift endpoint reported **PSI = 43.4** for a feature I
knew had barely moved. Population stability index is supposed to be ~0 for
identical distributions and small-but-nonzero for real shifts. Forty-three
is not a real value — it meant the estimator itself was broken.

**The trap.** The bug was invisible on happy paths. Feeding the detector
two *identical* samples returned a sane `0.000`, and a deliberate one-sigma
shift returned a plausible `0.98`. I had shipped it thinking the maths was
fine, because the unit tests I wrote were the unit tests the implementation
wanted to pass.

**Root cause.** The PSI implementation was doing every classic thing wrong
at once:

1. **Fixed 10 bins regardless of sample size.** With only 14 discrete
   samples (hourly aggregates over a day), that forced most bins empty —
   and empty bins produce infinite/divide-by-zero PSI contributions.
2. **Zero-mass bins.** A single outlier sample created a ratio like
   `0.01/0.00`, which exploded the log term.
3. **No smoothing.** No epsilon anywhere, so empty bins weren't damped.
4. **`density=True` on a histogram that was normalized again** — double
   normalization, so the "probabilities" summed to anything but 1.

**The debugging trail.** I stopped trusting the number and built a tiny
validation harness: identical → must be `0.000`; 1σ shift → must be small;
then the real case. The detector failed the *identical* check under the
real binning path (`max(3, n//5)` bins for 14 samples) even though it
passed at the default bin count. The fix:

- shared quantile edges across `(expected, observed)` — bins only where
  data exists;
- bin count scaled to sample size (`max(3, n // 5)`);
- Laplace smoothing on every bin;
- a single normalization, asserted to sum to 1.

**Validated:** identical → `0.000`, 1σ → `0.981`, real drift **43.4 →
3.86** — the value in the README's drift sample today.

**Lesson.** A drift detector is a *measurement instrument*. You validate an
instrument against ground truth, not against your tests' assumptions. If
your unit test for a numerical estimator doesn't cover the degenerate
case (empty bins, tiny samples, identical distributions), you haven't
tested the estimator — you've tested your confidence in it.

---

## Bug 2 — "AUC > 0.92." A number I couldn't defend.

**Symptom.** The model card shipped with a headline **"AUC > 0.92"**, and
it was repeated in the README and in talks. It was never measured.

**Root cause.** The number came from the design phase — a *target* value
written as an aspiration, which quietly became a "result" as it got copied
into downstream documents. Nobody reran it, because doing so meant touching
the training pipeline. It was, bluntly, a published figure I could not
defend if asked "show me the run."

**The trap.** In a buildathon, precision of language feels optional. It
isn't — the brief is built around *honest metrics*. A claim you can't
reproduce isn't just wrong; it signals you don't know the difference
between a target and a measurement.

**The debugging trail.** For the GNN benchmark series (36k synthetic
transactions, user-disjoint 80/10/10 split), I finally ran the numbers:

- **PR-AUC 0.198** (not 0.92); edge-free MLP baseline 0.056 → **3.5× lift**;
- AUC-ROC 0.692.

Two things were true at once, and the fix was to say both out loud: (a) the
"0.92" figure was fabricated-by-copy, and (b) the *real* number — a 3.5–4×
PR-AUC lift over an edge-free baseline — was actually a good story. Honesty
didn't weaken the story; it gave it a defensible spine. After the v1.1.0
iteration (target-user readout + five live features) the lift held: test
PR-AUC **0.4125**, still 4.0× vs the edge-free MLP. The correction is
footnoted in `models/payshield_gnn_v1_card.md`.

**Lesson.** Publish the number the run produced, or don't publish it. The
corrected 0.4125 is *smaller* than the aspirational 0.92 — and it is
infinitely more valuable, because a judge can verify it in five minutes.
Never let a number appear in a document you cannot trace to a script and a
log file.

---

## Bug 3 — The demo that failed in front of a friend. (Missing velocity keys)

**Symptom.** I was showing the "suspicious burst" scenario from the demo
script to a friend. The scorer returned `ALLOW` when the script's own
expected output said `BLOCK`. In front of a human being.

**The trap.** Everything worked in the test suite. Unit tests seeded
velocity data *directly into the Redis list keys* and the geo rules fired.
The demo seeder (`scripts/seed_demo_data.py`) populated the user and
merchant velocity surfaces but **never wrote `velocity:dev:*` or
`velocity:loc:*`** — the two surfaces the geo rules (`G-RULE-01` /
`G-RULE-02`) actually read. The "suspicious burst" scenario was built to
trigger geo velocity, so through the *real* path the demo exercised, it
could never fire.

**Root cause.** The tests and the demo used different entry points into
the store. Tests constructed the exact Redis keys they asserted against;
the demo seeded the world through a partial helper that silently skipped
two of five velocity surfaces. Nothing failed loudly — rules just never
fired, and `ALLOW` looked like a correct decision to anyone not holding the
expected-output table.

**The debugging trail.** I diffed the seeded keys against the rule engine's
read keys. The velocity rules read `velocity:user:*`, `velocity:dev:*`,
`velocity:loc:*`, plus merchant/device history; the seeder wrote only a
subset. Fix: seed prior location + device velocity history for the demo
archetypes so `Mumbai → Delhi` actually has a "within-window" baseline to
compare against. Commit: `fix(demo): bootstrap the seeder path and seed
geo/device velocity`.

**Lesson.** A demo is a test of the *real* path — it is not a second
entry point. When a scenario's expected output and its actual output
disagree, the first question is not "is the logic wrong" but "does the
scenario's setup actually reach the code path I think it does?" Seed-world
and assert-world must be the same world.

---

## What the three have in common

| Bug | Surface it broke | The fix that held |
|-----|------------------|-------------------|
| PSI estimator | Measurement correctness | Degenerate-case validation in the test suite |
| AUC > 0.92 | Honesty of claims | Run the metric or don't print it |
| Missing velocity keys | Demo realism | Demo exercises the same path tests do |

Each one was a small error with a large lesson: verify measurements on
adversarial inputs, publish only what you can reproduce, and never let the
demo diverge from the code it claims to demonstrate.