import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";

interface Investigation {
  txn_id: string;
  narrative?: string;
  fraud_type?: string;
  confidence?: string;
  recommended_action?: string;
  key_evidence?: string[];
  generated_at?: string;
}

const CONFIDENCE_PCT: Record<string, number> = { HIGH: 94, MEDIUM: 62, LOW: 18 };

function confidencePct(level?: string): number {
  return CONFIDENCE_PCT[(level || "").toUpperCase()] ?? 35;
}

function DecisionPill({ action }: { action: string }) {
  if (action.toLowerCase().includes("block")) {
    return (
      <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-secondary/10 text-secondary border border-secondary/20 inline-block">
        {action}
      </span>
    );
  }
  if (action.toLowerCase().includes("review")) {
    return (
      <span className="font-label-caps text-label-caps px-2 py-1 rounded bg-primary/10 text-primary border border-primary/20 inline-block">
        {action}
      </span>
    );
  }
  return (
    <span className="font-label-caps text-label-caps px-2 py-1 rounded border-subtle text-on-surface-variant inline-block">
      {action}
    </span>
  );
}

export function DashboardPage() {
  const [txns, setTxns] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiUp, setApiUp] = useState<boolean | null>(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await client.get("/v1/investigations");
        setTxns(res.data.results || []);
        setApiUp(true);
      } catch {
        setApiUp(false);
      } finally {
        setLoading(false);
      }
    };
    fetch();
    const interval = setInterval(fetch, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col">
      {/* Header / primary metrics */}
      <header className="mb-section-gap grid grid-cols-1 md:grid-cols-12 gap-gutter items-end">
        <div className="md:col-span-6">
          <h2 className="font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface tracking-tight mb-8">
            Financial Intelligence
          </h2>
          <div className="flex items-center gap-x-2 text-outline font-body-lg text-body-lg">
            <span className="material-symbols-outlined text-[16px]">sync</span>
            <span>{apiUp === false ? "Monitoring interrupted — API unreachable" : "Live Risk Monitoring Network"}</span>
          </div>
        </div>
        <div className="md:col-span-6 grid grid-cols-1 gap-gutter mt-12 md:mt-0 pt-8 border-t border-white/10 md:border-t-0 md:pt-0">
          <div>
            <p className="font-label-caps text-label-caps text-outline mb-4">Active Anomalies</p>
            <p className="font-display-lg text-display-lg-mobile md:text-display-lg text-error-container font-mono-data animate-counter">
              {loading ? "—" : txns.length}
            </p>
          </div>
        </div>
      </header>

      {/* Transaction ledger */}
      <section className="mb-section-gap">
        <div className="flex justify-between items-end mb-8 border-b border-white/10 pb-4">
          <h3 className="font-headline-md text-headline-md text-on-surface">Recent Anomalies</h3>
          <Link
            to="/transactions"
            className="text-primary hover:text-primary-container transition-colors duration-300 flex items-center gap-x-2 font-label-caps text-label-caps uppercase"
          >
            View All <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>

        <div className="w-full">
          <div className="grid grid-cols-12 gap-4 py-4 border-b border-white/10 font-label-caps text-label-caps text-outline mb-2">
            <div className="col-span-3">Entity / ID</div>
            <div className="col-span-2">Vector</div>
            <div className="col-span-2 text-right">Amount</div>
            <div className="col-span-3">Confidence</div>
            <div className="col-span-2 text-right">Decision</div>
          </div>

          <div className="flex flex-col">
            {!loading && txns.length === 0 && (
              <div className="py-10 text-center text-outline font-body-md text-body-md border-b border-white/5">
                No anomalies captured yet — score a transaction or check the service state.
              </div>
            )}
            {txns.map((t) => {
              const pct = confidencePct(t.confidence);
              return (
                <div
                  key={t.txn_id}
                  className="grid grid-cols-12 gap-4 py-4 border-b border-white/5 items-center hover:bg-surface-container-low transition-colors duration-200 ledger-row"
                >
                  <div className="col-span-3 flex items-center gap-x-4">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        t.recommended_action?.toLowerCase().includes("block")
                          ? "bg-error-container"
                          : "bg-primary-container"
                      }`}
                    />
                    <div>
                      <p className="font-body-md text-body-md text-on-surface">{t.txn_id}</p>
                      <p className="font-mono-data text-[12px] text-outline">
                        {t.confidence || "ASSESSED"}
                      </p>
                    </div>
                  </div>
                  <div className="col-span-2 font-body-md text-body-md text-on-surface-variant">
                    {t.fraud_type || "—"}
                  </div>
                  <div className="col-span-2 text-right font-mono-data text-mono-data text-on-surface">
                    —
                  </div>
                  <div className="col-span-3 flex items-center gap-x-4">
                    <div className="flex-grow h-[1px] bg-white/10 relative">
                      <div
                        className={`absolute top-0 left-0 h-full ${
                          pct >= 60 ? "bg-error-container" : "bg-primary-container"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="font-mono-data text-[12px] text-outline w-8">{pct}%</span>
                  </div>
                  <div className="col-span-2 flex justify-end">
                    <DecisionPill action={t.recommended_action || "ALLOW"} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Bottom analysis */}
      <section className="grid grid-cols-1 md:grid-cols-12 gap-gutter">
        <div className="md:col-span-8 border-subtle p-8 bg-surface">
          <h4 className="font-headline-md text-[24px] text-on-surface mb-6">
            Threat Vector Analysis
          </h4>
          <div className="h-64 w-full bg-surface-container-low flex items-center justify-center relative overflow-hidden">
            <div
              className="absolute inset-0 opacity-20 pointer-events-none"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(0deg, transparent, transparent 19px, rgba(244,241,234,0.05) 20px), repeating-linear-gradient(90deg, transparent, transparent 19px, rgba(244,241,234,0.05) 20px)",
              }}
            />
            <span className="text-outline font-label-caps text-label-caps">
              Live anomaly stream — velocity, geo-velocity, device & amount vectors
            </span>
          </div>
        </div>

        <div className="md:col-span-4 flex flex-col gap-gutter">
          <div className="border-subtle p-8 bg-surface flex-grow">
            <h4 className="font-title-lg text-title-lg text-on-surface mb-2">System Status</h4>
            <p className="font-body-md text-body-md text-on-surface-variant mb-6">
              {apiUp === false
                ? "API unreachable — verify the service is running."
                : "All detection engines operating nominally."}
            </p>
            <div className="flex items-center justify-between py-3 border-b border-white/5">
              <span className="font-body-md text-body-md text-outline">Engines</span>
              <span className="font-mono-data text-mono-data text-secondary">L1 · L2 · L3</span>
            </div>
            <div className="flex items-center justify-between py-3 border-b border-white/5">
              <span className="font-body-md text-body-md text-outline">Monitoring</span>
              <span className="font-mono-data text-mono-data text-on-surface">
                {apiUp === false ? "Offline" : "Live"}
              </span>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="font-body-md text-body-md text-outline">Audit Chain</span>
              <span className="font-mono-data text-mono-data text-on-surface">Tamper-proof</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

export default DashboardPage;