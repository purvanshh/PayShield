import { useState } from "react";

const CHAMPION = {
  user_return_rate_30d: 0.25,
  user_serial_returner_flag: 0.2,
  merchant_return_rate_30d: 0.15,
  txn_category_return_baseline: 0.15,
  txn_amount_risk: 0.1,
  user_cod_refusal_rate: 0.1,
  user_return_velocity_7d: 0.05,
};

const CHALLENGER = {
  user_return_rate_30d: 0.32,
  user_serial_returner_flag: 0.24,
  merchant_return_rate_30d: 0.15,
  txn_category_return_baseline: 0.15,
  txn_amount_risk: 0.06,
  user_cod_refusal_rate: 0.1,
  user_return_velocity_7d: 0.05,
};

const RESULT = {
  champion_n: 7260,
  challenger_n: 740,
  champion_mean: 719.76,
  challenger_mean: 532.72,
  delta: -187.05,
  t: -3.932,
  p_value: 0.0001,
  significant: true,
  recommendation: "keep (challenger is worse)",
};

export function ExperimentsPage() {
  const [showWeights, setShowWeights] = useState(false);

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          A/B Experiments
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          Champion / challenger evaluation for the return-risk scorer. Models are
          promoted on a controlled experiment — a Welch t-test on per-order cost
          saved — never on a training metric.
        </p>
      </div>

      {/* Recommendation */}
      <div className="border-subtle p-8 bg-surface mb-section-gap">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <p className="font-label-caps text-label-caps text-outline mb-3">
              Latest simulation verdict
            </p>
            <p className="font-display-lg-mobile text-display-lg-mobile text-on-surface leading-tight">
              Champion wins — keep current weights
            </p>
            <p className="font-body-md text-body-md text-on-surface-variant mt-3 max-w-2xl">
              The challenger reweighted return-history features upward, but it
              generated more false blocks at the review gate. The difference is
              statistically significant (p = {RESULT.p_value.toFixed(4)}), so the
              experiment says <span className="text-on-surface">promote nothing</span> —
              an honest negative result.
            </p>
          </div>
          <div>
            <span className="font-label-caps text-label-caps text-primary px-3 py-2 rounded bg-primary/10 border border-primary/20 inline-block">
              RECOMMENDATION · {RESULT.recommendation}
            </span>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-6 pt-6 border-t border-white/5">
          <div>
            <p className="font-label-caps text-label-caps text-outline">Champion mean</p>
            <p className="font-mono-data text-mono-data text-on-surface mt-1">
              ₹{RESULT.champion_mean.toFixed(2)} / order
            </p>
          </div>
          <div>
            <p className="font-label-caps text-label-caps text-outline">Challenger mean</p>
            <p className="font-mono-data text-mono-data text-on-surface mt-1">
              ₹{RESULT.challenger_mean.toFixed(2)} / order
            </p>
          </div>
          <div>
            <p className="font-label-caps text-label-caps text-outline">Δ savings</p>
            <p className="font-mono-data text-mono-data text-error mt-1">
              ₹{RESULT.delta.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="font-label-caps text-label-caps text-outline">p-value (Welch)</p>
            <p className="font-mono-data text-mono-data text-secondary mt-1">
              {RESULT.p_value.toFixed(4)}
            </p>
          </div>
        </div>
      </div>

      {/* Methodology */}
      <section className="mb-section-gap">
        <div className="flex justify-between items-end mb-8 border-b border-white/10 pb-4">
          <h3 className="font-headline-md text-headline-md text-on-surface">Methodology</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          {[
            {
              icon: "account_tree",
              title: "Deterministic bucketing",
              body: "Users are assigned to an arm via a stable hash, so a user always sees the same weights — no carry-over contamination between runs.",
            },
            {
              icon: "paid",
              title: "Merchant money as the metric",
              body: "Per-order cost saved (false-allow avoided minus false-block incurred) from docs/COST_MODEL.md, compared across arms.",
            },
            {
              icon: "functions",
              title: "Statistical significance",
              body: "Welch's unequal-variance t-test at α = 0.05. No promotion without significance; a negative result is still a decision.",
            },
          ].map((m) => (
            <div key={m.title} className="border-subtle bg-surface p-8">
              <span className="material-symbols-outlined text-primary mb-4">{m.icon}</span>
              <h4 className="font-title-lg text-title-lg text-on-surface mb-2">{m.title}</h4>
              <p className="font-body-md text-body-md text-on-surface-variant">{m.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Weights */}
      <section>
        <div className="flex justify-between items-end mb-8 border-b border-white/10 pb-4">
          <h3 className="font-headline-md text-headline-md text-on-surface">Weight Surfaces</h3>
          <button
            onClick={() => setShowWeights((v) => !v)}
            className="font-label-caps text-label-caps text-primary hover:text-primary-fixed uppercase"
          >
            {showWeights ? "Hide" : "Show"} weights
          </button>
        </div>
        {showWeights && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-gutter">
            {[
              { label: "Champion (current)", weights: CHAMPION, tense: "text-on-surface" },
              { label: "Challenger v1 (reflection-tuned)", weights: CHALLENGER, tense: "text-on-surface-variant" },
            ].map((arm) => (
              <div key={arm.label} className="border-subtle bg-surface p-8">
                <p className="font-label-caps text-label-caps text-outline mb-4">{arm.label}</p>
                {Object.entries(arm.weights).map(([name, w]) => (
                  <div key={name} className="flex items-center justify-between py-2 border-b border-white/5 font-mono-data text-mono-data">
                    <span className={`${arm.tense} text-[12px]`}>{name}</span>
                    <span className="text-on-surface">{w.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export default ExperimentsPage;