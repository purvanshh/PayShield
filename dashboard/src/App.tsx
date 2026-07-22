import React, { useEffect, useState } from "react";
import { TransactionTable } from "./components/TransactionTable";
import { FraudScoreGauge } from "./components/FraudScoreGauge";
import { SubgraphGraph } from "./components/SubgraphGraph";
import { InvestigationCard } from "./components/InvestigationCard";
import { PayShieldClient } from "./api/client";

const client = new PayShieldClient("payshield-dev-key-2026");

interface Alert {
  txn_id: string;
  user_id: string;
  amount: number;
  decision: string;
  fraud_probability: number;
  evidence: any;
}

const App: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [investigation, setInvestigation] = useState<any>(null);
  const [wsStatus, setWsStatus] = useState("disconnected");

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/v1/stream");
    ws.onopen = () => {
      setWsStatus("connected");
      ws.send(JSON.stringify({ action: "subscribe" }));
    };
    ws.onmessage = (event) => {
      const alert: Alert = JSON.parse(event.data);
      setAlerts((prev) => [alert, ...prev].slice(0, 100));
    };
    ws.onclose = () => setWsStatus("disconnected");
    return () => ws.close();
  }, []);

  const handleSelectAlert = async (alert: Alert) => {
    setSelectedAlert(alert);
    try {
      const report = await client.getInvestigation(alert.txn_id);
      setInvestigation(report);
    } catch {
      setInvestigation(null);
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "system-ui, sans-serif" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >
        <h1>PayShield Fraud Ops</h1>
        <span
          style={{
            color: wsStatus === "connected" ? "green" : "red",
            fontSize: "14px",
          }}
        >
          {wsStatus === "connected" ? "● Live" : "○ Disconnected"}
        </span>
      </header>

      <div style={{ display: "flex", gap: "20px" }}>
        <div style={{ flex: 2 }}>
          <h2>Alerts ({alerts.length})</h2>
          <TransactionTable
            transactions={alerts}
            onSelect={handleSelectAlert}
          />
        </div>

        <div style={{ flex: 1 }}>
          {selectedAlert && (
            <>
              <FraudScoreGauge score={selectedAlert.fraud_probability} />
              <p>
                <strong>Transaction:</strong> {selectedAlert.txn_id}
              </p>
              <p>
                <strong>User:</strong> {selectedAlert.user_id}
              </p>
              <p>
                <strong>Amount:</strong> ₹{selectedAlert.amount.toLocaleString()}
              </p>
              <p>
                <strong>Decision:</strong> {selectedAlert.decision}
              </p>

              {selectedAlert.evidence?.gnn_explanation?.evidence_subgraph && (
                <SubgraphGraph
                  elements={{
                    nodes: [
                      {
                        data: {
                          id: selectedAlert.user_id,
                          label: selectedAlert.user_id,
                        },
                      },
                    ],
                    edges: [],
                  }}
                />
              )}

              {investigation && (
                <InvestigationCard
                  narrative={investigation.narrative}
                  fraudType={investigation.fraud_type}
                  confidence={investigation.confidence}
                  recommendedAction={investigation.recommended_action}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default App;
