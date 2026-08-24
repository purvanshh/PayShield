# Application Answers — Razorpay AI Buildathon, Track 02

All 12 questions, pre-written and copy-paste ready. Keep this file open in
a second window while filling the form — never type answers live.

---

## Personal (questions 1–6)

1. **Full name** — (fill in)
2. **College** — (fill in)
3. **Graduation year** — (fill in)
4. **In-person from September: yes / no** — (fill in)
5. **6 or 12 months: your pick** — (fill in)
6. **Resume file** — PDF, under 2 MB (fill in)

## 7. Your track

**02 — AI Risk Manager**

## 8. Project name

**PayShield: AI Risk Manager**

## 9. What it solves

> Indian e-commerce merchants lose a significant share of GMV to returns —
> fashion runs 25–40%, and "serial returners" plus return fraud (wardrobing,
> empty-box) quietly eat margin order by order. PayShield is a
> **return-risk scorer built on Razorpay's infrastructure**: it scores every
> order *before it ships* (user history · merchant patterns · category
> baselines · 8 config-driven rules), and returns an explainable
> recommendation — "require prepaid", "flag for review", "ship" — with a
> per-feature breakdown (value · weight · contribution · source) in every
> response.
>
> The numbers are measured, not aspirational. On a 10,000-order
> chronological per-user hold-out: **PR-AUC 0.9806**, **0.9444 precision /
> 0.9125 recall** at the MEDIUM+ review gate (F1 0.9282), and **1.0000
> precision** at the strict gate. I translate precision into rupees
> ([`docs/COST_MODEL.md`](../docs/COST_MODEL.md)): the MEDIUM+ gate prevents
> ~1,086 returns/month for a 10k-order fashion merchant and **cuts return
> cost by 54.6% — ₹27,45,990/month saved (~₹2.75 lakh per 1,000 orders)**.
>
> PayShield ships as a pre-shipping layer inside a Razorpay merchant flow:
> one signed webhook (`order.paid` → `/webhooks/razorpay/return-risk`)
> triggers scoring; `refund.processed` feeds the label store for nightly
> retraining (`docs/RAZORPAY_INTEGRATION.md`). The wider platform extends the
> same audit chain to reactive fraud detection (L1 rules + GNN) and remedial
> chargeback response — but return-risk is the hero.

## 10. GitHub repo URL

(fill in the public URL — verify it loads in incognito before submitting)

## 11. 5-min pitch video, unlisted

(fill in the unlisted YouTube URL — test in incognito AND on a phone)

## 12. What broke, and how you got out

> Full stories with the debugging trail and lesson: [`docs/THREE_HARD_BUGS.md`](../docs/THREE_HARD_BUGS.md). The short versions:
>
> **1. "My drift detector was working." It wasn't.** The PSI endpoint
> reported 43.4 for a feature that barely moved. Every classic estimator
> bug was present at once (fixed bins, zero-mass bins, no smoothing, double
> normalization) — and invisible on the happy-path tests I'd written. Fix:
> validate the estimator against degenerate inputs (identical→0.000, 1σ→0.981,
> real case 43.4→3.86). Lesson: a measurement instrument is tested against
> ground truth, not your assumptions.
>
> **2. A number I couldn't defend.** The model card led with "AUC > 0.92" —
> aspirational, never measured. Running the actual benchmark gave PR-AUC
> 0.198 (later 0.4125 after the target-user-readout rework), which is a real
> 3.5–4× lift over an edge-free baseline. Corrected everywhere, footnoted in
> the model card. Lesson: publish the number the run produced, or don't
> publish one.
>
> **3. The demo failed in front of a friend.** The "suspicious burst"
> scenario returned ALLOW instead of BLOCK: the seeder never wrote the
> `velocity:dev:*` / `velocity:loc:*` keys the geo rules read, so the path
> the demo exercised could never trigger. Fix: seed the exact surfaces the
> rules read. Lesson: the demo and the tests must share one entry point into
> the store.

---

## Supporting documents checklist

- [ ] Resume PDF < 2 MB, typo-free
- [ ] Repo public — verified in incognito
- [ ] Video unlisted — verified in incognito + on phone
- [ ] Project name identical in repo, README, video, form ("PayShield: AI Risk Manager")
- [ ] Track number correct: 02 — AI Risk Manager
