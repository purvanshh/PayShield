import type { FeatureContribution, RuleTrigger } from "../types";

export function FeatureBreakdown({ features }: { features: Record<string, FeatureContribution> }) {
  const rows = Object.entries(features);
  if (rows.length === 0) return null;
  return (
    <div
      style={{
        padding: 12,
        border: "1px solid #1e293b",
        borderRadius: 12,
        background: "#0f172a",
        fontSize: 13,
      }}
    >
      <h4 style={{ margin: "0 0 8px", color: "#e2e8f0" }}>Feature breakdown</h4>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Feature", "Value", "Weight", "Contribution", "Source"].map((h) => (
              <th key={h} style={{ textAlign: "left", color: "#94a3b8", fontSize: 12 }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, f]) => (
            <tr key={name} style={{ borderTop: "1px solid #1e293b" }}>
              <td style={{ color: "#e2e8f0", padding: "4px 8px 4px 0" }}>{name}</td>
              <td style={{ color: "#e2e8f0", padding: "4px 8px" }}>{String(f.value)}</td>
              <td style={{ color: "#94a3b8", padding: "4px 8px" }}>{f.weight}</td>
              <td style={{ color: "#e2e8f0", padding: "4px 8px" }}>
                {(f.contribution ?? 0).toFixed(4)}
              </td>
              <td style={{ color: "#64748b", padding: "4px 8px" }}>{f.source ?? "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Recommendations({ rules, recommendations }: { rules: RuleTrigger[]; recommendations: string[] }) {
  const fired = rules.filter((r) => r.triggered);
  return (
    <div
      style={{
        padding: 12,
        border: "1px solid #1e293b",
        borderRadius: 12,
        background: "#0f172a",
      }}
    >
      <h4 style={{ margin: "0 0 8px", color: "#e2e8f0" }}>Rules fired</h4>
      {fired.length === 0 ? (
        <p style={{ color: "#64748b", fontSize: 13 }}>None</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 20, color: "#e2e8f0", fontSize: 13 }}>
          {fired.map((r) => (
            <li key={r.rule_id}>
              {r.rule_id} · {r.name}
              {r.action ? ` → ${r.action}` : ""}
            </li>
          ))}
        </ul>
      )}
      <h4 style={{ margin: "12px 0 8px", color: "#e2e8f0" }}>Recommendations</h4>
      <ul style={{ margin: 0, paddingLeft: 20, color: "#cbd5e1", fontSize: 13 }}>
        {recommendations.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
    </div>
  );
}
