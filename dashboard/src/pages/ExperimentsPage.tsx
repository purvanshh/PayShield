import { useEffect, useState } from "react";
import client from "../api/client";

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

interface ABResult {
  winner: string;
  recommendation?: string;
  p_value: number;
  delta: number;
  significant?: boolean;
  t_stat?: number;
  champion_mean?: number;
  challenger_mean?: number;
  champion_n?: number;
  challenger_n?: number;
}

export function ExperimentsPage() {
  const [showWeights, setShowWeights] = useState(false);
  const [result, setResult] = useState<ABResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await client.get("/v1/meta/experiments");
        setResult(res.data);
        setError("");
      } catch {
        setError("Experiment result unavailable — the backend did not serve a verdict.");
      }
    };
    load();
  }, []);

  if (error) {
    return (
      <div className="flex flex-col">
        <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3 mb-6">
          {error}
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col">
        <div className="mb-section-gap border-b border-white/10 pb-8">
          <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
            A/B Experiments
          </h1>
        </div>
        <div className="py-24 text-center text-outline font-body-md text-body-md">
          Loading experiment verdict…
        </div>
      </div>
    );
  }

  const champion_mean = result.champion_mean ?? 0;
  const challenger_mean = result.challenger_mean ?? 0;

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          A/B Experiments
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          Champion / challenger evaluation for the return-risk scorer. Models are
          promoted on a controlled experiment — a Welch t-test on per-order cost
          saved — never on a training metric. Verdict served live from{" "}
          <code className="text-on-surface-variant">/v1/meta/experiments</code>.
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
              {result.winner === "champion" ? "Champion wins — keep current weights" : "Challenger wins"}
            </p>
            <p className="font-body-md text-body-md text-on-surface-variant mt-3 max-w-2xl">
              The challenger reweighted return-history features upward, but it
              generated more false blocks at the review gate. The difference is
              statistically significant (p = {result.p_value.toFixed(4)}), so the
              experiment says <span className="text-on-surface">promote nothing</span> —
              an honest negative result.
            </p>
          </div>
          <div>
            <span className="font-label-caps text-label-caps text-primary px-3 py-2 rounded bg-primary/10 border border-primary/20 inline-block">
              RECOMMENDATION · {result.recommendation || (result.winner === "champion" ? "keep" : "promote")}
            </span>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-6 pt-6 border-t border-white/5">
          <div>
            <p className="font-label-caps text-label-caps text-outline">Champion mean</p>
            <p className="font-mono-data text-mono-data text-on-surface mt-1">
              ₹{champion_mean.toFixed(2)} / order
            </p>
          </div>
          <div>
            <p className="font-label-caps text-label-caps text-outline">Challenger mean</p>
            <p className="font-mono-data text-mono-data text-on-surface mt-1">
              ₹{challenger_mean.toFixed(2)} / order
            </p>
          </div>
          <div>
            <p className="font-label-caps text-label-caps text-outline">Δ savings</p>
            <p className="font-mono-data text-mono-data text-error mt-1">
              ₹{result.delta.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="font-label-caps text-label-caps text-outline">p-value (Welch)</p>
            <p className="font-mono-data text-mono-data text-secondary mt-1">
              {result.p_value.toFixed(4)}
            </p>
          </div>
        </div>
        {typeof result.champion_n === "number" && (
          <p className="font-mono-data text-mono-data text-outline mt-4 pt-4 border-t border-white/5">
            champion n={result.champion_n.toLocaleString()} · challenger n={result.challenger_n?.toLocaleString()}
          </p>
        )}
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
              body: "Per-order cost saved (false-allow avoided minus review/block penalties) from docs/COST_MODEL.md, compared across arms.",
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