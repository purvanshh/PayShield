import { useEffect, useState } from "react";
import client from "../api/client";
import type { FraudScoreResponse, AlertPayload } from "../types";
import { TransactionTable } from "../components/TransactionTable";
import { FraudScoreGauge } from "../components/FraudScoreGauge";
import { InvestigationCard } from "../components/InvestigationCard";
import { AlertToast } from "../components/AlertToast";
import { useWebSocket } from "../hooks/useWebSocket";

export function DashboardPage() {
  const [txns, setTxns] = useState<FraudScoreResponse[]>([]);
  const [selected, setSelected] = useState<FraudScoreResponse | null>(null);
  useWebSocket();

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await client.get("/v1/investigations");
        setTxns(res.data.results || []);
      } catch {
        /* ignore */
      }
    };
    fetch();
    const interval = setInterval(fetch, 5000);
    return () => clearInterval(interval);
  }, []);

  const columns = [
    { key: "txn_id", label: "Txn ID", sortable: true },
    { key: "fraud_probability", label: "Probability", sortable: true },
    { key: "decision", label: "Decision", sortable: true },
    { key: "layer_triggered", label: "Layer", sortable: true },
    { key: "latency_ms", label: "Latency (ms)", sortable: true },
  ];

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0f172a" }}>
      <AlertToast />
      <div style={{ flex: 1, padding: 24, overflow: "auto" }}>
        <h1 style={{ color: "#f8fafc", fontSize: 24, marginBottom: 24 }}>Fraud Dashboard</h1>
        <div style={{ display: "flex", gap: 24 }}>
          <div style={{ flex: selected ? 0.6 : 1 }}>
            <div
              style={{
                background: "#1e293b",
                borderRadius: 8,
                padding: 16,
                border: "1px solid #334155",
              }}
            >
              <h2 style={{ color: "#f8fafc", fontSize: 16, marginBottom: 12 }}>Recent Transactions</h2>
              <TransactionTable
                data={txns as any}
                columns={columns}
                onRowClick={(row) => setSelected(row as unknown as FraudScoreResponse)}
              />
            </div>
          </div>
          {selected && (
            <div style={{ flex: 0.4 }}>
              <FraudScoreGauge probability={selected.fraud_probability} decision={selected.decision} />
              <div style={{ marginTop: 16 }}>
                <InvestigationCard
                  report={{
                    txn_id: selected.txn_id,
                    narrative: (selected.evidence as any)?.narrative || "No narrative available",
                    fraud_type: "OTHER",
                    confidence: selected.fraud_probability > 0.85 ? "HIGH" : selected.fraud_probability > 0.5 ? "MEDIUM" : "LOW",
                    recommended_action: selected.decision,
                    key_evidence: [],
                    reasoning: "",
                    generated_at: new Date().toISOString(),
                  }}
                  onFeedback={(decision) => {
                    console.log("Feedback:", selected.txn_id, decision);
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
