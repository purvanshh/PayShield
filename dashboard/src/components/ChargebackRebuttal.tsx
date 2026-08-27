import type { ChargebackRespondData } from "../types";

const RESPONSE_COLORS: Record<string, string> = {
  REJECT: "#16a34a",
  PARTIAL: "#f59e0b",
  ACCEPT: "#64748b",
};

export function ChargebackRebuttal({ rebuttal }: { rebuttal: ChargebackRespondData }) {
  const color = RESPONSE_COLORS[rebuttal.response_type] ?? "#64748b";
  return (
    <div
      style={{
        padding: 16,
        border: "1px solid #1e293b",
        borderRadius: 12,
        background: "#0f172a",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, color: "#e2e8f0" }}>Chargeback Rebuttal</h3>
        <span
          style={{
            padding: "2px 14px",
            borderRadius: 12,
            fontWeight: 600,
            background: color,
            color: "#0f172a",
          }}
        >
          {rebuttal.response_type}
        </span>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        <div>
          <label style={{ fontSize: 12, color: "#94a3b8" }}>Confidence</label>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0" }}>
            {(rebuttal.confidence_score * 100).toFixed(0)}%
          </div>
        </div>
        <div>
          <label style={{ fontSize: 12, color: "#94a3b8" }}>Evidence completeness</label>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0" }}>
            {(rebuttal.evidence_completeness * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      {rebuttal.warnings.length > 0 && (
        <div style={{ padding: 8, borderRadius: 6, background: "rgba(245,158,11,.12)", fontSize: 13, color: "#fcd34d" }}>
          {rebuttal.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      <div>
        <h4 style={{ margin: "0 0 6px", color: "#e2e8f0" }}>AI narrative</h4>
        <p style={{ margin: 0, fontSize: 13, color: "#cbd5e1" }}>{rebuttal.narrative.summary}</p>
        <ul style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 12, color: "#94a3b8" }}>
          {rebuttal.narrative.key_evidence.slice(0, 6).map((ev, i) => (
            <li key={i}>{ev}</li>
          ))}
        </ul>
      </div>

      <div>
        <h4 style={{ margin: "0 0 6px", color: "#e2e8f0" }}>Audit trail</h4>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", color: "#94a3b8" }}>Time</th>
              <th style={{ textAlign: "left", color: "#94a3b8" }}>Action</th>
              <th style={{ textAlign: "left", color: "#94a3b8" }}>Agent</th>
            </tr>
          </thead>
          <tbody>
            {rebuttal.audit_trail.map((entry, i) => (
              <tr key={i} style={{ borderTop: "1px solid #1e293b" }}>
                <td style={{ color: "#94a3b8", padding: "4px 8px 4px 0" }}>
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </td>
                <td style={{ color: "#e2e8f0", padding: "4px 8px" }}>{entry.action}</td>
                <td style={{ color: "#64748b", padding: "4px 8px" }}>{entry.agent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
