import type { InvestigationReport } from "../types";

interface Props {
  report: InvestigationReport;
  onFeedback?: (decision: string) => void;
}

export function InvestigationCard({ report, onFeedback }: Props) {
  const confidenceColor =
    report.confidence === "HIGH" ? "#16a34a" : report.confidence === "MEDIUM" ? "#f59e0b" : "#dc2626";

  return (
    <div
      style={{
        background: "#1e293b",
        borderRadius: 8,
        padding: 20,
        border: "1px solid #334155",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: "#f8fafc", fontSize: 18 }}>Investigation Report</h3>
        <span
          style={{
            padding: "2px 10px",
            borderRadius: 12,
            fontSize: 12,
            fontWeight: 600,
            background: confidenceColor,
            color: "#fff",
          }}
        >
          {report.confidence}
        </span>
      </div>

      <div style={{ color: "#f8fafc", lineHeight: 1.6, marginBottom: 16 }}>
        {report.narrative}
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 16, fontSize: 13 }}>
        <div>
          <span style={{ color: "#94a3b8" }}>Fraud Type: </span>
          <span style={{ color: "#f8fafc", fontWeight: 600 }}>{report.fraud_type}</span>
        </div>
        <div>
          <span style={{ color: "#94a3b8" }}>Action: </span>
          <span style={{ color: "#f8fafc", fontWeight: 600 }}>{report.recommended_action}</span>
        </div>
      </div>

      {report.key_evidence.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ color: "#94a3b8", fontSize: 12, fontWeight: 600, marginBottom: 8 }}>
            KEY EVIDENCE
          </div>
          <ul style={{ margin: 0, paddingLeft: 16, color: "#cbd5e1", fontSize: 13 }}>
            {report.key_evidence.map((ev, i) => (
              <li key={i}>{ev}</li>
            ))}
          </ul>
        </div>
      )}

      {report.reasoning && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ color: "#94a3b8", fontSize: 12, fontWeight: 600, marginBottom: 8 }}>
            REASONING
          </div>
          <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5 }}>{report.reasoning}</div>
        </div>
      )}

      {onFeedback && (
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button
            onClick={() => onFeedback("ALLOW")}
            style={{
              padding: "8px 16px",
              background: "#16a34a",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 13,
            }}
          >
            Overturn to Allow
          </button>
          <button
            onClick={() => onFeedback("BLOCK")}
            style={{
              padding: "8px 16px",
              background: "#dc2626",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 13,
            }}
          >
            Confirm Block
          </button>
        </div>
      )}

      <div style={{ color: "#475569", fontSize: 11, marginTop: 12 }}>
        Model: {report.model_version || "1.0.0"} · Generated: {new Date(report.generated_at).toLocaleString()}
      </div>
    </div>
  );
}
