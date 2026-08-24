import { useMemo } from "react";

interface Scenario {
  key: string;
  label: string;
  description: string;
  assumptions: {
    aov: number;
    returnRate: number;
    logistics: number;
    restocking: number;
    service: number;
    gatewayPct: number;
    cac: number;
    churn: number;
    ltv: number;
    diversion: number;
  };
}

const SCENARIOS: Scenario[] = [
  {
    key: "fashion",
    label: "Fashion",
    description: "High category baseline, mid AOV (Myntra/Flipkart-style).",
    assumptions: {
      aov: 2500,
      returnRate: 0.18,
      logistics: 120,
      restocking: 80,
      service: 45,
      gatewayPct: 0.02,
      cac: 180,
      churn: 0.15,
      ltv: 3000,
      diversion: 0.7,
    },
  },
  {
    key: "electronics",
    label: "Electronics",
    description: "Low volume, high AOV, buy-now-return-later dynamics.",
    assumptions: {
      aov: 8000,
      returnRate: 0.12,
      logistics: 180,
      restocking: 120,
      service: 60,
      gatewayPct: 0.02,
      cac: 250,
      churn: 0.12,
      ltv: 6000,
      diversion: 0.7,
    },
  },
  {
    key: "grocery",
    label: "Grocery",
    description: "High frequency, tiny AOV, low category return rate.",
    assumptions: {
      aov: 800,
      returnRate: 0.04,
      logistics: 80,
      restocking: 40,
      service: 25,
      gatewayPct: 0.02,
      cac: 40,
      churn: 0.2,
      ltv: 900,
      diversion: 0.65,
    },
  },
];

// Measured MEDIUM+ operating point (10k-order hold-out).
const OP_PRECISION = 0.9444;
const OP_RECALL = 0.9125;
const ORDERS = 10_000;

function evaluate(a: Scenario["assumptions"]) {
  const falseAllow = a.aov + a.logistics + a.restocking + a.service + a.aov * a.gatewayPct;
  const falseBlock = a.aov + a.aov * a.gatewayPct + a.cac + a.churn * a.ltv;
  const totalReturns = Math.floor(ORDERS * a.returnRate);
  const caught = Math.round(OP_RECALL * totalReturns);
  const falseBlocks = Math.round(caught * (1 - OP_PRECISION));
  const trueCaught = caught - falseBlocks;
  const prevented = Math.round(trueCaught * a.diversion);
  const remaining = totalReturns - prevented;
  const baseline = totalReturns * falseAllow;
  const payshield = remaining * falseAllow + falseBlocks * falseBlock;
  const savings = baseline - payshield;
  return {
    falseAllow,
    falseBlock,
    totalReturns,
    caught,
    falseBlocks,
    trueCaught,
    prevented,
    remaining,
    baseline,
    payshield,
    savings,
    roi: baseline ? (savings / baseline) * 100 : 0,
  };
}

const inr = (n: number) => Math.round(n).toLocaleString("en-IN");

export function CostModelPage() {
  const results = useMemo(
    () => SCENARIOS.map((s) => ({ label: s.label, value: evaluate(s.assumptions) })),
    []
  );

  const sensitivity = useMemo(() => {
    const f = SCENARIOS[0].assumptions;
    return (
      [
        [1500, 0.12],
        [2500, 0.18],
        [4000, 0.25],
      ] as Array<[number, number]>
    ).map(([aov, rate]) => {
      const a = { ...f, aov, returnRate: rate };
      return { aov, rate, ...evaluate(a) };
    });
  }, []);

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap border-b border-white/10 pb-8">
        <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
          Return-Risk Cost Model
        </h1>
        <p className="font-body-lg text-body-lg text-outline max-w-3xl">
          Precision and recall translated into merchant money. At the MEDIUM+
          review gate (0.9444 precision · 0.9125 recall) the scorer prevents
          returns before they ship — savings computed live below from the same
          assumptions as <span className="text-on-surface-variant">docs/COST_MODEL.md</span>.
        </p>
      </div>

      {/* Headline */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter mb-section-gap">
        <div className="md:col-span-2 border-subtle p-8 bg-surface">
          <p className="font-label-caps text-label-caps text-outline mb-4">
            Fashion merchant · 10,000 orders / month
          </p>
          <p className="font-display-lg text-display-lg-mobile md:text-display-lg text-primary leading-none animate-counter">
            ₹{inr(results[0].value.savings)}
          </p>
          <p className="font-body-md text-body-md text-on-surface-variant mt-3">
            saved per month vs. no model — {results[0].value.roi.toFixed(1)}% return-cost
            reduction, {inr(results[0].value.prevented)} returns prevented, only{" "}
            {results[0].value.falseBlocks} false blocks.
          </p>
          <div className="mt-6 flex flex-wrap gap-6 pt-6 border-t border-white/5">
            <div>
              <p className="font-label-caps text-label-caps text-outline">Cost / false allow</p>
              <p className="font-mono-data text-mono-data text-on-surface mt-1">
                ₹{inr(results[0].value.falseAllow)}
              </p>
            </div>
            <div>
              <p className="font-label-caps text-label-caps text-outline">Cost / false block</p>
              <p className="font-mono-data text-mono-data text-on-surface mt-1">
                ₹{inr(results[0].value.falseBlock)}
              </p>
            </div>
            <div>
              <p className="font-label-caps text-label-caps text-outline">Baseline spend</p>
              <p className="font-mono-data text-mono-data text-on-surface mt-1">
                ₹{inr(results[0].value.baseline)}
              </p>
            </div>
            <div>
              <p className="font-label-caps text-label-caps text-outline">With PayShield</p>
              <p className="font-mono-data text-mono-data text-on-surface mt-1">
                ₹{inr(results[0].value.payshield)}
              </p>
            </div>
          </div>
        </div>

        <div className="border-subtle p-8 bg-surface flex flex-col justify-between">
          <div>
            <p className="font-label-caps text-label-caps text-outline mb-4">
              Cost asymmetry drives the threshold
            </p>
            <p className="font-body-md text-body-md text-on-surface-variant">
              A false block (₹{inr(results[0].value.falseBlock)}) costs ~14% more than a
              false allow (₹{inr(results[0].value.falseAllow)}). The optimizer therefore
              prefers precision at the review tier — not a crude block gate.
            </p>
          </div>
          <div className="pt-6 mt-6 border-t border-white/5">
            <div className="flex items-center justify-between">
              <span className="font-body-md text-body-md text-outline">Precision</span>
              <span className="font-mono-data text-mono-data text-secondary">
                {OP_PRECISION.toFixed(4)}
              </span>
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="font-body-md text-body-md text-outline">Recall</span>
              <span className="font-mono-data text-mono-data text-secondary">
                {OP_RECALL.toFixed(4)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Scenario sweep */}
      <section className="mb-section-gap">
        <div className="flex justify-between items-end mb-8 border-b border-white/10 pb-4">
          <h3 className="font-headline-md text-headline-md text-on-surface">Scenario Sweep</h3>
          <span className="font-mono-data text-mono-data text-outline">MEDIUM+ gate</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          {results.map((r) => (
            <div key={r.label} className="border-subtle bg-surface p-8 flex flex-col">
              <p className="font-label-caps text-label-caps text-outline uppercase">{r.label}</p>
              <p className="font-body-md text-body-md text-on-surface-variant mt-1 mb-6">
                {SCENARIOS.find((s) => s.label === r.label)!.description}
              </p>
              <p className="font-display-lg-mobile text-display-lg-mobile text-primary leading-none">
                ₹{inr(r.value.savings)}
              </p>
              <p className="font-mono-data text-mono-data text-outline mt-2">/ month saved</p>
              <div className="mt-auto pt-6 flex items-end justify-between">
                <div>
                  <p className="font-label-caps text-label-caps text-outline">Annual</p>
                  <p className="font-mono-data text-mono-data text-on-surface mt-1">
                    ₹{inr(r.value.savings * 12)}
                  </p>
                </div>
                <span className="font-mono-data text-mono-data text-secondary">
                  {r.value.roi.toFixed(1)}% ROI
                </span>
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
          {sensitivity.map((s) => (
            <div
              key={s.aov}
              className="grid grid-cols-2 md:grid-cols-12 gap-4 py-4 border-b border-white/5 items-center"
            >
              <div className="col-span-1 md:col-span-3 font-mono-data text-mono-data text-on-surface">
                ₹{s.aov.toLocaleString("en-IN")}
              </div>
              <div className="col-span-1 md:col-span-3 font-mono-data text-mono-data text-on-surface-variant">
                {(s.rate * 100).toFixed(0)}%
              </div>
              <div className="col-span-2 md:col-span-3 text-right font-mono-data text-mono-data text-primary">
                ₹{inr(s.savings)}
              </div>
              <div className="col-span-2 md:col-span-3 text-right font-mono-data text-mono-data text-secondary">
                {s.roi.toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default CostModelPage;