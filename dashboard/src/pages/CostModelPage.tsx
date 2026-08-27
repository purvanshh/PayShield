import { useEffect, useState } from "react";
import client from "../api/client";

interface CostScenario {
  key: string;
  label: string;
  description: string;
  aov: number;
  return_rate: number;
  monthly_savings: number;
  annual_savings: number;
  roi_pct: number;
  prevented: number;
  wrong_flags: number;
  baseline_cost: number;
  payshield_cost: number;
  false_allow_cost: number;
}

interface CostSensitivityRow {
  aov: number;
  return_rate: number;
  monthly_savings: number;
  annual_savings: number;
  roi_pct: number;
}

interface MaturityRow {
  maturity: string;
  vertical: string;
  aov: number;
  return_rate: number;
  pr_auc: number | null;
  roc_auc: number | null;
  precision_at_050: number;
  recall_at_050: number;
  monthly_savings: number;
  annual_savings: number;
  roi_pct: number;
}

interface MaturityScenarios {
  orders: number;
  generated_at: string;
  rows: MaturityRow[];
  note: string;
}

interface CostReport {
  operating_point: {
    name: string;
    threshold: number;
    precision: number;
    recall: number;
    action: string;
    wrong_flag_cost: number;
  };
  scenarios: CostScenario[];
  sensitivity: CostSensitivityRow[];
  orders: number;
  generated_at?: string;
  maturity_scenarios?: MaturityScenarios;
}

const STAGE_LABELS: Record<string, string> = {
  basic: "Stage 1: Basic",
  enriched: "Stage 2: Enriched",
  premium: "Stage 3: Premium",
};

const inr = (n: number) => Math.round(n).toLocaleString("en-IN");

export function CostModelPage() {
  const [report, setReport] = useState<CostReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await client.get("/v1/meta/return-risk/cost");
        setReport(res.data);
        setError("");
      } catch {
        setError("Cost model unavailable — the backend did not serve a result.");
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

  if (!report) {
    return (
      <div className="py-24 text-center text-outline font-body-md text-body-md">
        Loading cost model…
      </div>
    );
  }

  const fashion = report.scenarios.find((s) => s.key === "fashion") ?? report.scenarios[0];
  const op = report.operating_point;
  const scenarios = report.scenarios;
  const sensitivity = report.sensitivity;
  const maturity = report.maturity_scenarios;

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Return-Risk Cost Model
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          Precision and recall translated into merchant money. Served live from
          the authoritative calculator (<code className="text-on-surface-variant">/v1/meta/return-risk/cost</code>) — no
          frontend copies. At the MEDIUM+ review gate ({op.precision.toFixed(4)} precision ·{" "}
          {op.recall.toFixed(4)} recall) the scorer prevents returns before they ship.
        </p>
      </div>

      {/* Headline */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter mb-section-gap">
        <div className="md:col-span-2 border-subtle p-8 bg-surface">
          <p className="font-label-caps text-label-caps text-outline mb-4">
            Fashion merchant · {report.orders.toLocaleString("en-IN")} orders / month
          </p>
          <p className="font-display-lg text-display-lg-mobile md:text-display-lg text-primary leading-none animate-counter">
            ₹{inr(fashion.monthly_savings)}
          </p>
          <p className="font-body-md text-body-md text-on-surface-variant mt-3">
            saved per month vs. no model — {fashion.roi_pct.toFixed(1)}% return-cost
            reduction, {inr(fashion.prevented)} returns prevented, only{" "}
            {fashion.wrong_flags} wrong flags (₹{op.wrong_flag_cost.toLocaleString("en-IN")} each).
          </p>
          <div className="mt-6 flex flex-wrap gap-6 pt-6 border-t border-white/5">
            <div>
              <p className="font-label-caps text-label-caps text-outline">Baseline spend</p>
              <p className="font-mono-data text-mono-data text-on-surface mt-1">₹{inr(fashion.baseline_cost)}</p>
            </div>
            <div>
              <p className="font-label-caps text-label-caps text-outline">With PayShield</p>
              <p className="font-mono-data text-mono-data text-on-surface mt-1">₹{inr(fashion.payshield_cost)}</p>
            </div>
            <div>
              <p className="font-label-caps text-label-caps text-outline">Annual savings</p>
              <p className="font-mono-data text-mono-data text-on-surface mt-1">₹{inr(fashion.annual_savings)}</p>
            </div>
          </div>
        </div>

        <div className="border-subtle p-8 bg-surface flex flex-col justify-between">
          <div>
            <p className="font-label-caps text-label-caps text-outline mb-4">
              Cost asymmetry drives the threshold
            </p>
            <p className="font-body-md text-body-md text-on-surface-variant">
              A wrong MEDIUM flag is a <span className="text-on-surface">review</span> — it costs
              ₹{op.wrong_flag_cost.toLocaleString("en-IN")} of operator time while the order still
              ships. Only the HIGH/prepaid gate carries the full false-block penalty.
            </p>
          </div>
          <div className="pt-6 mt-6 border-t border-white/5">
            <div className="flex items-center justify-between">
              <span className="font-body-md text-body-md text-outline">Precision</span>
              <span className="font-mono-data text-mono-data text-secondary">{op.precision.toFixed(4)}</span>
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="font-body-md text-body-md text-outline">Recall</span>
              <span className="font-mono-data text-mono-data text-secondary">{op.recall.toFixed(4)}</span>
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="font-body-md text-body-md text-outline">Review gate</span>
              <span className="font-mono-data text-mono-data text-on-surface">{op.threshold.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Progressive Merchant Maturity */}
      {maturity && maturity.rows.length > 0 && (
        <section className="mb-section-gap">
          <div className="flex justify-between items-end mb-8 border-b border-white/10 pb-4">
            <div>
              <h3 className="font-headline-md text-headline-md text-on-surface">
                Progressive Merchant Maturity
              </h3>
              <p className="font-body-md text-body-md text-outline mt-2 max-w-2xl">
                Three named merchant segments with identical model architecture —
                only the data source (observed features + unobserved-variance budget)
                changes. ROC-AUC is measured, never hardcoded.
              </p>
            </div>
          </div>
          <div className="w-full">
            <div className="grid grid-cols-12 gap-4 py-4 border-b border-white/10 font-label-caps text-label-caps text-outline mb-2">
              <div className="col-span-3">Scenario</div>
              <div className="col-span-2">Vertical</div>
              <div className="col-span-1 text-right">PR-AUC</div>
              <div className="col-span-1 text-right">ROC-AUC</div>
              <div className="col-span-1 text-right">P@0.50</div>
              <div className="col-span-1 text-right">R@0.50</div>
              <div className="col-span-2 text-right">Net ₹/month</div>
              <div className="col-span-1 text-right">ROI</div>
            </div>
            {maturity.rows.map((r, i) => (
              <div
                key={`${r.maturity}-${r.vertical}-${i}`}
                className="grid grid-cols-12 gap-4 py-4 border-b border-white/5 items-center"
              >
                <div className="col-span-3 font-body-md text-body-md text-on-surface">
                  {STAGE_LABELS[r.maturity] ?? r.maturity}
                </div>
                <div className="col-span-2 font-mono-data text-mono-data text-on-surface-variant capitalize">
                  {r.vertical}
                </div>
                <div className="col-span-1 text-right font-mono-data text-mono-data text-on-surface">
                  {r.pr_auc?.toFixed(4) ?? "n/a"}
                </div>
                <div className="col-span-1 text-right font-mono-data text-mono-data text-on-surface">
                  {r.roc_auc?.toFixed(4) ?? "n/a"}
                </div>
                <div className="col-span-1 text-right font-mono-data text-mono-data text-outline">
                  {r.precision_at_050.toFixed(3)}
                </div>
                <div className="col-span-1 text-right font-mono-data text-mono-data text-outline">
                  {r.recall_at_050.toFixed(3)}
                </div>
                <div className="col-span-2 text-right font-mono-data text-mono-data text-primary">
                  ₹{inr(r.monthly_savings)}
                </div>
                <div className="col-span-1 text-right font-mono-data text-mono-data text-secondary">
                  {r.roi_pct.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>
          <p className="font-body-sm text-body-sm text-outline mt-4">
            Stage 1 is the honest floor; Stage 3 is a premium merchant with mature
            instrumentation. The ₹ lift comes from improved measured P/R at the
            0.50 gate — not from base-rate or AOV changes.
          </p>
        </section>
      )}

      {/* Scenario sweep */}
      <section className="mb-section-gap">
        <div className="flex justify-between items-end mb-8 border-b border-white/10 pb-4">
          <h3 className="font-headline-md text-headline-md text-on-surface">Scenario Sweep</h3>
          <span className="font-mono-data text-mono-data text-outline">
            MEDIUM+ gate · {op.threshold.toFixed(2)}
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          {scenarios.map((s) => (
            <div key={s.key} className="border-subtle bg-surface p-8 flex flex-col">
              <p className="font-label-caps text-label-caps text-outline uppercase">{s.label}</p>
              <p className="font-body-md text-body-md text-on-surface-variant mt-1 mb-6">{s.description}</p>
              <p className="font-display-lg-mobile text-display-lg-mobile text-primary leading-none">
                ₹{inr(s.monthly_savings)}
              </p>
              <p className="font-mono-data text-mono-data text-outline mt-2">/ month saved</p>
              <div className="mt-auto pt-6 flex items-end justify-between">
                <div>
                  <p className="font-label-caps text-label-caps text-outline">Annual</p>
                  <p className="font-mono-data text-mono-data text-on-surface mt-1">₹{inr(s.annual_savings)}</p>
                </div>
                <span className="font-mono-data text-mono-data text-secondary">{s.roi_pct.toFixed(1)}% ROI</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Sensitivity */}
      <section>
        <h3 className="font-headline-md text-headline-md text-on-surface mb-8 border-b border-white/10 pb-4">
          Sensitivity · AOV × return rate
        </h3>
        <div className="w-full">
          <div className="grid grid-cols-12 gap-4 py-4 border-b border-white/10 font-label-caps text-label-caps text-outline mb-2">
            <div className="col-span-4 md:col-span-3">AOV</div>
            <div className="col-span-4 md:col-span-3">Return rate</div>
            <div className="col-span-4 md:col-span-3 text-right">Monthly savings</div>
            <div className="col-span-4 md:col-span-3 text-right">ROI</div>
          </div>
          {sensitivity.map((row) => (
            <div
              key={row.aov}
              className="grid grid-cols-2 md:grid-cols-12 gap-4 py-4 border-b border-white/5 items-center"
            >
              <div className="col-span-1 md:col-span-3 font-mono-data text-mono-data text-on-surface">
                ₹{row.aov.toLocaleString("en-IN")}
              </div>
              <div className="col-span-1 md:col-span-3 font-mono-data text-mono-data text-on-surface-variant">
                {(row.return_rate * 100).toFixed(0)}%
              </div>
              <div className="col-span-2 md:col-span-3 text-right font-mono-data text-mono-data text-primary">
                ₹{inr(row.monthly_savings)}
              </div>
              <div className="col-span-2 md:col-span-3 text-right font-mono-data text-mono-data text-secondary">
                {row.roi_pct.toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default CostModelPage;