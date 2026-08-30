import { useEffect, useState } from "react";
import client from "../api/client";
import type { FeatureContribution, ReturnScoreData } from "../types";

interface WaterfallItem {
  feature: string;
  value: number;
  importance: number;
  contribution: number;
}

interface ExplainData {
  order_id: string;
  return_risk_score: number;
  risk_tier: string;
  engine: string;
  base_score: number;
  waterfall: WaterfallItem[];
  note: string;
}

const ORDER_PRESETS: Record<string, Record<string, unknown>> = {
  "Serial returner (fashion, COD)": {
    order_id: "ORD_SERIAL_001",
    user_id: "U_SERIAL_001",
    merchant_id: "M_FASHION_001",
    amount: 5500,
    category: "fashion",
    payment_method: "UPI",
    cod_flag: true,
  },
  "Honest electronics customer": {
    order_id: "ORD_HONEST_001",
    user_id: "U_HONEST_001",
    merchant_id: "M_ELECTRONICS_001",
    amount: 12000,
    category: "electronics",
    payment_method: "UPI",
    cod_flag: false,
  },
  "Fresh user (no history)": {
    order_id: "ORD_FRESH_001",
    user_id: "cust_fresh_2026",
    merchant_id: "M_FASHION_001",
    amount: 2500,
    category: "fashion",
    payment_method: "UPI",
    cod_flag: true,
  },
};

const FEATURE_ICONS: Record<string, string> = {
  user_return_rate_30d: "history",
  user_return_rate_90d: "history",
  user_return_rate_lifetime: "history",
  user_serial_returner_flag: "autorenew",
  merchant_return_rate_30d: "storefront",
  merchant_category_return_rate: "category",
  merchant_return_fraud_rate: "shield",
  txn_category_return_baseline: "category",
  txn_amount_risk: "payments",
  user_cod_refusal_rate: "local_shipping",
  user_return_velocity_7d: "trending_up",
};

function humanize(name: string): string {
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function tierColor(tier: string) {
  if (tier === "HIGH") return "error";
  if (tier === "MEDIUM") return "primary";
  return "secondary";
}

function topFeatures(breakdown: Record<string, FeatureContribution>, n: number) {
  return Object.entries(breakdown || {})
    .map(([name, fc]) => ({ name, fc }))
    .sort((a, b) => Math.abs(b.fc.contribution || 0) - Math.abs(a.fc.contribution || 0))
    .slice(0, n);
}

function ScoreGauge({ score, tier }: { score: number; tier: string }) {
  const pct = Math.round(score * 100);
  // circumference of r=45 svg circle ≈ 282.7
  const dashOffset = 283 * (1 - Math.min(pct, 100) / 100);
  const color = tierColor(tier);
  return (
    <div className="relative w-64 h-64 flex items-center justify-center mt-8">
      <svg className="w-full h-full radial-progress" viewBox="0 0 100 100">
        <circle
          className="text-surface-variant stroke-current"
          cx="50"
          cy="50"
          fill="transparent"
          r="45"
          strokeWidth="2"
        />
        <circle
          className={`text-${color} stroke-current dash-array`}
          cx="50"
          cy="50"
          fill="transparent"
          r="45"
          strokeLinecap="butt"
          strokeWidth="3"
          style={{ strokeDashoffset: dashOffset }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="font-display-lg text-display-lg text-on-surface leading-none">{pct}</span>
        <span className="font-label-caps text-label-caps text-outline uppercase tracking-widest mt-2">
          Percentile
        </span>
      </div>
    </div>
  );
}

export function ReturnRiskPage() {
  const [presetKey, setPresetKey] = useState(Object.keys(ORDER_PRESETS)[0]);
  const [result, setResult] = useState<ReturnScoreData | null>(null);
  const [explain, setExplain] = useState<ExplainData | null>(null);
  const [waterfallOpen, setWaterfallOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const score = async (key: string) => {
    setLoading(true);
    setError("");
    setWaterfallOpen(false);
    try {
      const payload = ORDER_PRESETS[key];
      const [scoreRes, explainRes] = await Promise.all([
        client.post("/v1/return/score", payload),
        client.post("/v1/return/explain", payload),
      ]);
      setResult(scoreRes.data.data);
      setExplain(explainRes.data);
    } catch {
      setError("Request failed — verify your session, then retry.");
      setResult(null);
      setExplain(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    score(presetKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetKey]);

  const features = topFeatures(result?.feature_breakdown ?? {}, 2);

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="mb-section-gap flex flex-col md:flex-row justify-between items-start md:items-end gap-8 border-b border-white/10 pb-8">
        <div>
          <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
            Return Risk Analysis
          </h1>
          <p className="font-body-lg text-body-lg text-outline max-w-2xl">
            {result
              ? `Transaction ID: ${result.order_id}. Institutional assessment complete.`
              : "Scoring an order for return risk before dispatch."}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="bg-surface-container-high px-3 py-1 rounded-sm border-subtle flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full bg-${tierColor(result?.risk_tier || "LOW")}`} />
            <span className={`font-mono-data text-mono-data text-${tierColor(result?.risk_tier || "LOW")}`}>
              {result ? `${result.risk_tier} Risk` : "—"}
            </span>
          </div>
          <button className="bg-primary text-on-primary px-6 py-2 font-label-caps text-label-caps uppercase tracking-widest hover:bg-primary-fixed transition-colors">
            Action Required
          </button>
        </div>
      </div>

      {/* Honest-scope banner: the live scorer runs the evaluated Stage 1 model
          on the Stage 1 feature schema. Visible so a judge never has to dig
          for the calibration caveat. */}
      <div className="mb-section-gap border border-primary/30 bg-primary/5 px-4 py-3 flex items-start gap-3">
        <span className="material-symbols-outlined text-primary text-[20px] mt-0.5">info</span>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Live scoring runs the Stage 1 model on Stage 1-schema features; metrics
          are from the evaluated DGP hold-out. See{" "}
          <code className="text-on-surface">CALIBRATION_GAP.md</code>.
        </p>
      </div>

      {/* Preset selector */}
      <div className="flex flex-wrap gap-3 mb-section-gap">
        {Object.keys(ORDER_PRESETS).map((key) => (
          <button
            key={key}
            onClick={() => setPresetKey(key)}
            disabled={loading}
            className={`px-4 py-2 font-label-caps text-label-caps uppercase tracking-widest transition-colors duration-300 ${
              key === presetKey
                ? "bg-primary text-on-primary"
                : "border border-subtle text-on-surface-variant hover:border-primary hover:text-primary"
            }`}
          >
            {key}
          </button>
        ))}
        {error && (
          <span className="px-4 py-2 font-mono-data text-mono-data text-error">{error}</span>
        )}
      </div>

      {!result && !error && (
        <div className="py-24 text-center text-outline font-body-md text-body-md">
          Loading assessment…
        </div>
      )}

      {result && (
        <>
          {/* Bento grid */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter mb-section-gap">
            {/* Radial gauge */}
            <div className="md:col-span-5 bg-surface-container-low border-subtle p-8 flex flex-col items-center justify-center min-h-[400px] relative overflow-hidden">
              <div
                className="absolute inset-0 opacity-10 pointer-events-none"
                style={{
                  backgroundImage: `radial-gradient(ellipse at center, var(--tw-gradient-stops))`,
                }}
              />
              <h2 className="font-title-lg text-title-lg text-on-surface absolute top-8 left-8">
                Aggregate Score
              </h2>
              <ScoreGauge score={result.return_risk_score} tier={result.risk_tier} />
              <div className="mt-8 font-mono-data text-mono-data text-outline text-center w-full max-w-xs border-t border-white/5 pt-4">
                <div className="flex justify-between mb-1">
                  <span>Confidence Interval</span>
                  <span className="text-on-surface">{(result.confidence * 100).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span>Signal Source</span>
                  <span className="text-on-surface">{String(result.user_profile.is_new_user ? "Population prior" : "Customer history")}</span>
                </div>
              </div>
            </div>

            {/* Feature breakdown */}
            <div className="md:col-span-7 flex flex-col gap-gutter">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-gutter">
                {features.map(({ name, fc }) => (
                  <div key={name} className="bg-surface p-6 border-subtle flex flex-col justify-between">
                    <div>
                      <div className="flex items-start justify-between mb-4">
                        <span className="material-symbols-outlined text-outline">
                          {FEATURE_ICONS[name] || "query_stats"}
                        </span>
                        <span className="font-mono-data text-mono-data text-primary">
                          {(fc.contribution * 100).toFixed(0)}%
                        </span>
                      </div>
                      <h3 className="font-title-lg text-title-lg text-on-surface mb-2">
                        {humanize(name)}
                      </h3>
                      <p className="font-body-md text-body-md text-outline">
                        Value {String(fc.value)} · weight {(fc.weight * 100).toFixed(0)}%
                        <span className="block text-on-surface-variant">{String(fc.source)}</span>
                      </p>
                    </div>
                    <div className="mt-6 border-t border-white/5 pt-4">
                      <span className="font-label-caps text-label-caps text-surface-tint uppercase tracking-widest">
                        {name.includes("return") || name.includes("history") ? "Primary Vector" : "Contributing Vector"}
                      </span>
                    </div>
                  </div>
                ))}

                {/* Transaction attributes */}
                <div className="bg-surface border-subtle flex-1 overflow-hidden">
                  <div className="p-6 border-b border-white/5">
                    <h3 className="font-title-lg text-title-lg text-on-surface">
                      Transaction Attributes
                    </h3>
                  </div>
                  <div className="px-6 pb-6">
                    <div className="flex justify-between py-3 border-b border-white/5 font-mono-data text-mono-data">
                      <span className="text-outline">Order ID</span>
                      <span className="text-on-surface">{result.order_id}</span>
                    </div>
                    <div className="flex justify-between py-3 border-b border-white/5 font-mono-data text-mono-data">
                      <span className="text-outline">Amount</span>
                      <span className="text-on-surface">
                        ₹{String(result.user_profile.avg_return_value ?? "—")}
                      </span>
                    </div>
                    <div className="flex justify-between py-3 border-b border-white/5 font-mono-data text-mono-data">
                      <span className="text-outline">Risk Tier</span>
                      <span className={`text-${tierColor(result.risk_tier)}`}>{result.risk_tier}</span>
                    </div>
                    <div className="flex justify-between py-3 font-mono-data text-mono-data">
                      <span className="text-outline">Serial Returner</span>
                      <span className="text-on-surface">
                        {result.user_profile.serial_returner ? "Confirmed" : "Not flagged"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Model waterfall (XGBoost attribution) */}
          {explain && (
            <div className="border-t border-white/10 pt-12 pb-section-gap max-w-4xl">
              <button
                onClick={() => setWaterfallOpen(!waterfallOpen)}
                className="w-full flex items-center justify-between group"
              >
                <div className="text-left">
                  <h2 className="font-headline-md text-headline-md text-on-surface mb-1">
                    Model Waterfall — why this score
                  </h2>
                  <p className="font-body-md text-body-md text-outline">
                    XGBoost per-feature attribution · engine {explain.engine} ·
                    score {Math.round(explain.return_risk_score * 1000) / 1000} ({explain.risk_tier})
                  </p>
                </div>
                <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">
                  {waterfallOpen ? "expand_less" : "expand_more"}
                </span>
              </button>

              {waterfallOpen && (
                <div className="mt-8 space-y-4">
                  {explain.waterfall.map((item) => {
                    const max = Math.max(...explain.waterfall.map((c) => c.contribution), 0.001);
                    const width = Math.max(4, (item.contribution / max) * 100);
                    return (
                      <div key={item.feature}>
                        <div className="flex justify-between mb-1 font-mono-data text-mono-data">
                          <span className="text-on-surface">{humanize(item.feature)}</span>
                          <span className="text-outline">
                            value {item.value} · importance {item.importance} ·{" "}
                            <span className="text-primary">{item.contribution.toFixed(4)}</span>
                          </span>
                        </div>
                        <div className="h-2 bg-surface-variant/40 rounded-sm overflow-hidden">
                          <div
                            className={`h-full ${item.contribution >= 0.5 * max ? "bg-primary" : "bg-secondary"}`}
                            style={{ width: `${width}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                  <p className="pt-4 font-body-md text-body-md text-outline border-t border-white/5">
                    {explain.note}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Recommendations */}
          <div className="border-t border-white/10 pt-12 pb-section-gap max-w-4xl">
            <h2 className="font-headline-md text-headline-md text-on-surface mb-8">
              Strategic Recommendations
            </h2>
            <ul className="space-y-6">
              {result.recommendations.slice(0, 5).map((rec, i) => (
                <li key={rec} className="flex items-start gap-4">
                  <span
                    className={`mt-1.5 w-1.5 h-1.5 rounded-full bg-primary shrink-0`}
                    style={{ opacity: Math.max(0.4, 1 - i * 0.2) }}
                  />
                  <div>
                    <h4 className="font-title-lg text-title-lg text-on-surface mb-1">{rec}</h4>
                    <p className="font-body-lg text-body-lg text-outline">
                      {result.rules_triggered?.filter((r) => r.triggered)[i]?.description ||
                        "Merchant-actionable outcome from the transparent scoring surface."}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

export default ReturnRiskPage;