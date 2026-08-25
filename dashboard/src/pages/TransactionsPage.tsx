import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";

interface Investigation {
  txn_id: string;
  narrative?: string;
  fraud_type?: string;
  confidence?: string;
  recommended_action?: string;
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

export function TransactionsPage() {
  const [txns, setTxns] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      try {
        const res = await client.get("/v1/investigations", { params: { page_size: 100 } });
        setTxns(res.data.results || []);
        setError("");
      } catch {
        setError("Could not load transactions — verify your session.");
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, []);

  return (
    <div className="flex flex-col">
      <div className="mb-section-gap flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-white/10 pb-8">
        <div>
          <h1 className="font-display-lg-mobile md:font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-2">
            Risk Ledger
          </h1>
          <p className="font-body-lg text-body-lg text-outline max-w-2xl">
            Every scored anomalous transaction, ranked by confidence.
          </p>
        </div>
        <Link
          to="/fraud"
          className="font-label-caps text-label-caps text-primary hover:text-primary-fixed uppercase tracking-widest flex items-center gap-2"
        >
          Back to Dashboard <span className="material-symbols-outlined text-[16px]">arrow_back</span>
        </Link>
      </div>

      {error && (
        <div className="border border-error/30 bg-error/5 text-error font-body-md text-body-md px-4 py-3 mb-6">
          {error}
        </div>
      )}

      <div className="w-full">
        <div className="grid grid-cols-12 gap-4 py-4 border-b border-white/10 font-label-caps text-label-caps text-outline mb-2">
          <div className="col-span-4 md:col-span-3">Entity / ID</div>
          <div className="col-span-2 hidden md:block">Vector</div>
          <div className="col-span-3">Confidence</div>
          <div className="col-span-2">Assessed</div>
          <div className="col-span-3 md:col-span-2 text-right">Decision</div>
        </div>

        <div className="flex flex-col">
          {!loading && txns.length === 0 && (
            <div className="py-10 text-center text-outline font-body-md text-body-md border-b border-white/5">
              No anomalies yet — score a transaction first.
            </div>
          )}
          {txns.map((t) => {
            const pct = confidencePct(t.confidence);
            return (
              <div
                key={t.txn_id}
                className="grid grid-cols-12 gap-4 py-4 border-b border-white/5 items-center hover:bg-surface-container-low transition-colors duration-200"
              >
                <div className="col-span-4 md:col-span-3 flex items-center gap-x-4">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      t.recommended_action?.toLowerCase().includes("block")
                        ? "bg-error-container"
                        : "bg-primary-container"
                    }`}
                  />
                  <div className="min-w-0">
                    <p className="font-body-md text-body-md text-on-surface truncate">{t.txn_id}</p>
                    <p className="font-mono-data text-[12px] text-outline md:hidden">
                      {t.fraud_type || "ANOMALY"}
                    </p>
                  </div>
                </div>
                <div className="col-span-2 hidden md:block font-body-md text-body-md text-on-surface-variant">
                  {t.fraud_type || "—"}
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
                <div className="col-span-2 font-mono-data text-mono-data text-on-surface-variant text-[12px]">
                  {t.generated_at ? new Date(t.generated_at).toLocaleDateString() : "—"}
                </div>
                <div className="col-span-3 md:col-span-2 flex justify-end">
                  <DecisionPill action={t.recommended_action || "ALLOW"} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default TransactionsPage;