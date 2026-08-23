import { useEffect, useState } from "react";
import client from "../api/client";
import type { ChargebackRespondData } from "../types";
import { ChargebackRebuttal } from "../components/ChargebackRebuttal";

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
  const [preset, setPreset] = useState(Object.keys(DISPUTE_PRESETS)[0]);
  const [result, setResult] = useState<ChargebackRespondData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const respond = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await client.post("/v1/chargeback/respond", DISPUTE_PRESETS[preset]);
      setResult(res.data.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "respond failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    respond();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 960 }}>
      <h1 style={{ margin: 0 }}>Chargeback Response</h1>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {Object.keys(DISPUTE_PRESETS).map((p) => (
          <button key={p} onClick={() => setPreset(p)} disabled={loading}>
            {p}
          </button>
        ))}
      </div>
      {error && <p style={{ color: "#fca5a5" }}>{error}</p>}
      {result && <ChargebackRebuttal rebuttal={result} />}
    </div>
  );
}

export default ChargebackPage;
