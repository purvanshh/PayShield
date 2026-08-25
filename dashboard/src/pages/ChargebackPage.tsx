import { useEffect, useState } from "react";
import client from "../api/client";
import type { ChargebackRespondData } from "../types";

const DISPUTE_PRESETS: Record<string, Record<string, string>> = {
  "Winnable (clean txn, Visa 10.4)": {
    dispute_id: "CB_WINNABLE_001",
    payment_id: "pay_CLEAN_001",
    transaction_id: "TXN_CLEAN_001",
    network: "VISA",
    reason_code: "10.4",
    reason_description: "Fraud - Card Not Present",
    response_deadline: "2026-09-20T00:00:00",
  },
  "Weak case (new user, UPI)": {
    dispute_id: "CB_WEAK_001",
    payment_id: "pay_NEW_001",
    transaction_id: "TXN_NEW_001",
    network: "UPI",
    reason_code: "FRAUD",
    reason_description: "Fraudulent Transaction",
    response_deadline: "2026-08-28T00:00:00",
  },
};

export function ChargebackPage() {
  const [presetKey, setPresetKey] = useState("Weak case (new user, UPI)");
  const [result, setResult] = useState<ChargebackRespondData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const respond = async (key: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await client.post("/v1/chargeback/respond", DISPUTE_PRESETS[key]);
      setResult(res.data.data);
    } catch {
      setError("Request failed — verify your session, then retry.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    respond(presetKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetKey]);

  const winPct = result ? Math.round(result.confidence_score * 100) : 0;
  const trustScore = result ? Math.round(result.evidence_completeness * 100) : 0;
  const payload = result?.razorpay_payload ?? {};

  const ledgerRows: Array<[string, string, boolean]> = result
    ? [
        ["Dispute ID", result.dispute_id, false],
        ["Response Type", result.response_type, true],
        ["Evidence Completeness", `${result.evidence_completeness.toFixed(2)}`, false],
        ["Network", String(DISPUTE_PRESETS[presetKey].network), false],
        ["Reason Code", String(DISPUTE_PRESETS[presetKey].reason_description), false],
      ]
    : [];

  return (
    <div className="flex flex-col">
      {/* Header */}
      <header className="mb-gutter md:mb-section-gap flex flex-col md:flex-row md:items-end justify-between border-b border-white/10 pb-8 gap-8">
        <div>
          <h1 className="font-display-lg text-display-lg-mobile md:text-display-lg text-on-surface mb-4">
            Chargeback Rebuttal Engine
          </h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl">
            Automated evidence compilation and narrative generation for dispute case{" "}
            {result ? `#${result.dispute_id}` : "—"}.
          </p>
        </div>
        <div className="flex flex-col items-end">
          <span className="font-label-caps text-label-caps text-outline mb-2">
            WIN PROBABILITY
          </span>
          <div className="font-display-lg text-display-lg text-primary leading-none">
            {result ? `${winPct}%` : "—"}
          </div>
        </div>
      </header>

      {/* Preset selector */}
      <div className="flex flex-wrap gap-3 mb-section-gap">
        {Object.keys(DISPUTE_PRESETS).map((key) => (
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
          Assembling rebuttal…
        </div>
      )}

      {result && (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter">
          {/* Narrative + ledger */}
          <div className="md:col-span-8 flex flex-col gap-gutter">
            <section className="border border-white/10 bg-surface-container-low p-8 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-primary opacity-50" />
              <div className="flex justify-between items-center mb-6 border-b border-white/5 pb-4">
                <h2 className="font-title-lg text-title-lg text-on-surface">
                  AI Rebuttal Narrative
                </h2>
                <span
                  className="material-symbols-outlined text-primary"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  smart_toy
                </span>
              </div>

              {result.warnings.length > 0 && (
                <div className="mb-6 border border-error/30 bg-error/5 px-4 py-3">
                  {presetKey.startsWith("Weak") && !result.warnings.some((w) => w.toLowerCase().includes("graph")) && (
                    <p className="font-mono-data text-mono-data text-error">
                      ! GRAPH_EVIDENCE_INCOMPLETE — graph layer skipped for this new user
                    </p>
                  )}
                  {result.warnings.map((w) => (
                    <p key={w} className="font-mono-data text-mono-data text-error">
                      ! {w}
                    </p>
                  ))}
                </div>
              )}

              <div className="font-body-md text-body-md text-on-surface-variant space-y-4 leading-relaxed">
                <p>{result.narrative?.summary || "Summarising the dispute evidence…"}</p>
                <p>{result.narrative?.full_report || ""}</p>
              </div>

              {result.narrative?.key_evidence?.length ? (
                <div className="mt-6 pt-4 border-t border-white/5">
                  <span className="font-label-caps text-label-caps text-outline uppercase tracking-widest">
                    Key Evidence
                  </span>
                  <ul className="mt-3 space-y-1">
                    {result.narrative.key_evidence.map((ev) => (
                      <li key={ev} className="font-body-md text-body-md text-on-surface-variant">
                        • {ev}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="mt-8 pt-6 border-t border-white/5 flex gap-4">
                <button className="bg-primary text-on-primary font-label-caps text-label-caps px-6 py-3 uppercase tracking-wider hover:bg-primary-container transition-colors">
                  Submit Response
                </button>
                <button className="bg-transparent border border-outline text-on-surface font-label-caps text-label-caps px-6 py-3 uppercase tracking-wider hover:border-primary transition-colors">
                  Edit Narrative
                </button>
              </div>
            </section>

            {/* Transaction ledger */}
            <section className="border border-white/10 bg-surface p-8">
              <h3 className="font-label-caps text-label-caps text-outline mb-6">
                Transaction Ledger
              </h3>
              <div className="flex flex-col">
                {ledgerRows.map(([label, value, highlight]) => (
                  <div key={label} className="flex justify-between py-3 border-b border-white/5">
                    <span className="font-body-md text-body-md text-on-surface-variant">{label}</span>
                    <span
                      className={`font-mono-data text-mono-data ${
                        highlight ? "text-secondary" : "text-on-surface"
                      }`}
                    >
                      {value}
                    </span>
                  </div>
                ))}
              </div>
              {Object.keys(payload).length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/5">
                  <span className="font-label-caps text-label-caps text-outline uppercase tracking-widest">
                    Razorpay Payload
                  </span>
                  <pre className="mt-3 font-mono-data text-mono-data text-on-surface-variant text-[12px] overflow-x-auto max-h-40">
                    {JSON.stringify(payload, null, 2)}
                  </pre>
                </div>
              )}
            </section>
          </div>

          {/* Audit trail + trust */}
          <div className="md:col-span-4 flex flex-col gap-gutter">
            <section className="border border-white/10 bg-surface p-8">
              <h3 className="font-label-caps text-label-caps text-outline mb-6">Audit Trail</h3>
              <div className="relative pl-6 before:absolute before:inset-0 before:ml-[9px] before:-translate-x-px before:h-full before:w-px before:bg-white/10">
                {result.audit_trail.map((entry, i) => (
                  <div key={`${entry.action}-${i}`} className="relative pb-6 last:pb-0">
                    <div
                      className={`absolute left-[-29px] w-3 h-3 rounded-full border-2 border-surface mt-1 ${
                        i === result.audit_trail.length - 1 ? "bg-error" : "bg-secondary"
                      }`}
                    />
                    <div className="font-mono-data text-mono-data text-outline mb-1">
                      {new Date(entry.timestamp).toLocaleTimeString()} · {entry.agent}
                    </div>
                    <div className="font-body-md text-body-md text-on-surface">{entry.action}</div>
                    {entry.detail && (
                      <div className="font-body-md text-body-md text-on-surface-variant text-[12px]">
                        {entry.detail}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <section className="border border-white/10 bg-surface p-8 flex items-center gap-4">
              <span
                className="material-symbols-outlined text-outline text-3xl"
                style={{ fontVariationSettings: "'FILL' 0" }}
              >
                fingerprint
              </span>
              <div>
                <div className="font-label-caps text-label-caps text-outline">
                  Evidence Completeness
                </div>
                <div className="font-title-lg text-title-lg text-on-surface">{trustScore}/100</div>
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

export default ChargebackPage;