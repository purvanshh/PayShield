import { useEffect, useState } from "react";
import client from "../api/client";
import type { ReturnScoreData } from "../types";
import { ReturnRiskGauge } from "../components/ReturnRiskGauge";
import { FeatureBreakdown, Recommendations } from "../components/FeatureBreakdown";

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
};

export function ReturnRiskPage() {
  const [preset, setPreset] = useState(Object.keys(ORDER_PRESETS)[0]);
  const [result, setResult] = useState<ReturnScoreData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const score = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await client.post("/v1/return/score", ORDER_PRESETS[preset]);
      setResult(res.data.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "scoring failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    score();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 960 }}>
      <h1 style={{ margin: 0 }}>Return Risk Scoring</h1>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {Object.keys(ORDER_PRESETS).map((p) => (
          <button key={p} onClick={() => setPreset(p)} disabled={loading}>
            {p}
          </button>
        ))}
      </div>
      {error && <p style={{ color: "#fca5a5" }}>{error}</p>}
      {result && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <div style={{ minWidth: 320, flex: 1 }}>
            <ReturnRiskGauge
              score={result.return_risk_score}
              tier={result.risk_tier}
              confidence={result.confidence}
            />
          </div>
          <div style={{ flex: 2, display: "flex", flexDirection: "column", gap: 16 }}>
            <FeatureBreakdown features={result.feature_breakdown} />
            <Recommendations
              rules={result.rules_triggered}
              recommendations={result.recommendations}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default ReturnRiskPage;
