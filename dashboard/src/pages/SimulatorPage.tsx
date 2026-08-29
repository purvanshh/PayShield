import { useEffect, useRef, useState } from "react";
import client from "../api/client";

interface SimulateResult {
  return_risk_score: number;
  risk_tier: string;
  stage: string;
  model_path: string | null;
  features: Record<string, number>;
}

const CATEGORIES = ["fashion", "electronics", "groceries", "home", "beauty", "sports", "footwear"];
const METHODS = ["UPI", "CARD", "COD", "NETBANKING", "WALLET"];

function tierColor(tier: string) {
  if (tier === "HIGH") return "error";
  if (tier === "MEDIUM") return "primary";
  return "secondary";
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <div className="flex justify-between mb-1 font-label-caps text-label-caps">
        <span className="text-outline uppercase tracking-widest">{label}</span>
        <span className="text-on-surface font-mono-data text-mono-data">
          {step >= 1 ? value.toFixed(0) : value.toFixed(2)}
          {unit ?? ""}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--primary)]"
      />
    </label>
  );
}

export function SimulatorPage() {
  const [stage, setStage] = useState<"basic" | "premium">("basic");
  const [amount, setAmount] = useState(12000);
  const [aov, setAov] = useState(74500);
  const [r30, setR30] = useState(0.15);
  const [r90, setR90] = useState(0.15);
  const [days, setDays] = useState(12);
  const [device, setDevice] = useState(0.5);
  const [rating, setRating] = useState(4.0);
  const [delivery, setDelivery] = useState(3);
  const [category, setCategory] = useState("fashion");
  const [method, setMethod] = useState("UPI");
  const [result, setResult] = useState<SimulateResult | null>(null);
  const [error, setError] = useState("");
  const debounce = useRef<number | null>(null);

  const simulate = () => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(async () => {
      try {
        const payload = {
          amount,
          user_aov: aov,
          category,
          payment_method: method,
          user_return_rate_30d: r30,
          user_return_rate_90d: r90,
          days_since_last_order: days,
          device_fingerprint_match: device,
          product_rating: rating,
          delivery_speed_days: delivery,
          stage,
        };
        const res = await client.post("/v1/return/simulate", payload);
        setResult(res.data);
        setError("");
      } catch {
        setError("Simulation failed — is the API reachable?");
      }
    }, 250);
  };

  useEffect(() => {
    simulate();
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, amount, aov, r30, r90, days, device, rating, delivery, category, method]);

  const score = result?.return_risk_score ?? 0;
  const pct = Math.round(score * 100);

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Calibration Simulator
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          Drag the feature sliders and watch the XGBoost score move. Toggle the
          stage to compare the production 7-feature model against the premium
          9-feature model (product rating + delivery speed observed) — a live
          look at how better data changes risk.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 mb-section-gap">
        {(["basic", "premium"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStage(s)}
            className={`px-4 py-2 font-label-caps text-label-caps uppercase tracking-widest transition-colors duration-300 ${
              stage === s
                ? "bg-primary text-on-primary"
                : "border border-subtle text-on-surface-variant hover:border-primary hover:text-primary"
            }`}
          >
            Stage {s === "basic" ? "1 · Basic (7 features)" : "3 · Premium (9 features)"}
          </button>
        ))}
        {error && <span className="px-4 py-2 font-mono-data text-mono-data text-error">{error}</span>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter">
        {/* Controls */}
        <div className="md:col-span-7 bg-surface-container-low border-subtle p-8">
          <div className="flex flex-col gap-6">
            <Slider label="Return rate 30d" value={r30} min={0} max={1} step={0.01} unit="%" onChange={setR30} />
            <Slider label="Return rate 90d" value={r90} min={0} max={1} step={0.01} unit="%" onChange={setR90} />
            <Slider label="Order amount" value={amount} min={1000} max={100000} step={1000} unit=" ₹" onChange={setAmount} />
            <Slider label="User AOV" value={aov} min={5000} max={150000} step={5000} unit=" ₹" onChange={setAov} />
            <Slider label="Days since last order" value={days} min={0} max={120} step={1} unit="d" onChange={setDays} />
            <Slider label="Device fingerprint match" value={device} min={0} max={1} step={0.05} onChange={setDevice} />
            {stage === "premium" && (
              <>
                <Slider label="Product rating" value={rating} min={1} max={5} step={0.1} unit="★" onChange={setRating} />
                <Slider label="Delivery speed" value={delivery} min={0} max={14} step={0.5} unit="d" onChange={setDelivery} />
              </>
            )}

            <div className="grid grid-cols-2 gap-6 pt-2 border-t border-white/10">
              <label className="block">
                <span className="font-label-caps text-label-caps text-outline uppercase tracking-widest block mb-1">
                  Category
                </span>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full bg-surface border border-subtle text-on-surface px-3 py-2"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="font-label-caps text-label-caps text-outline uppercase tracking-widest block mb-1">
                  Payment method
                </span>
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                  className="w-full bg-surface border border-subtle text-on-surface px-3 py-2"
                >
                  {METHODS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </div>

        {/* Result */}
        <div className="md:col-span-5 bg-surface-container-low border-subtle p-8 flex flex-col items-center justify-center min-h-[400px]">
          <span className="font-label-caps text-label-caps text-outline uppercase tracking-widest mb-2">
            Score · Stage {stage}
          </span>
          <div className="flex items-baseline gap-1">
            <span className={`font-display-lg text-display-lg ${tierColor(result?.risk_tier ?? "LOW")}`}>
              {pct}
            </span>
            <span className="text-outline font-body-lg text-body-lg">/ 100</span>
          </div>
          <span className={`font-label-caps text-label-caps px-2 py-1 rounded mt-3 bg-${tierColor(result?.risk_tier ?? "LOW")}/10 text-${tierColor(result?.risk_tier ?? "LOW")} border border-${tierColor(result?.risk_tier ?? "LOW")}/20`}>
            {result?.risk_tier ?? "LOW"} RISK
          </span>
          <div className="mt-8 w-full max-w-sm border-t border-white/10 pt-4">
            {result ? (
              Object.entries(result.features).map(([name, value]) => (
                <div key={name} className="flex justify-between py-1 font-mono-data text-mono-data text-sm">
                  <span className="text-outline">{name}</span>
                  <span className="text-on-surface">{Number(value).toFixed(3)}</span>
                </div>
              ))
            ) : (
              <p className="text-outline font-body-md text-body-md text-center">Adjust a slider to score.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default SimulatorPage;
