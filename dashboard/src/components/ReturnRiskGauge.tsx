interface Props {
  score: number;
  tier: "LOW" | "MEDIUM" | "HIGH";
  confidence: number;
}

const TIER_COLORS: Record<string, string> = {
  LOW: "#16a34a",
  MEDIUM: "#f59e0b",
  HIGH: "#dc2626",
};

export function ReturnRiskGauge({ score, tier, confidence }: Props) {
  const color = TIER_COLORS[tier] ?? "#16a34a";
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - score);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
        padding: 16,
        border: "1px solid #1e293b",
        borderRadius: 12,
        background: "#0f172a",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
        <span style={{ fontWeight: 600, color: "#e2e8f0" }}>Return Risk</span>
        <span
          style={{
            padding: "2px 12px",
            borderRadius: 12,
            fontSize: 12,
            fontWeight: 600,
            background: color,
            color: "#0f172a",
          }}
        >
          {tier}
        </span>
      </div>
      <svg width={160} height={160} viewBox="0 0 160 160">
        <circle cx="80" cy="80" r={radius} fill="none" stroke="#1e293b" strokeWidth={12} />
        <circle
          cx="80"
          cy="80"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 80 80)"
          style={{ transition: "stroke-dashoffset 0.5s ease, stroke 0.3s ease" }}
        />
        <text x="80" y="75" textAnchor="middle" fill="#f8fafc" fontSize={28} fontWeight={700}>
          {(score * 100).toFixed(0)}%
        </text>
        <text x="80" y="100" textAnchor="middle" fill="#94a3b8" fontSize={12}>
          return risk
        </text>
      </svg>
      <div style={{ width: "100%" }}>
        <label style={{ fontSize: 12, color: "#94a3b8" }}>
          Confidence: {(confidence * 100).toFixed(0)}%
        </label>
        <div style={{ height: 6, borderRadius: 3, background: "#1e293b", overflow: "hidden" }}>
          <div
            style={{
              width: `${confidence * 100}%`,
              height: "100%",
              background: color,
              borderRadius: 3,
            }}
          />
        </div>
      </div>
      {tier === "HIGH" && (
        <div
          style={{
            width: "100%",
            padding: 8,
            borderRadius: 6,
            background: "rgba(220,38,38,.15)",
            color: "#fca5a5",
            fontSize: 13,
          }}
        >
          High return risk detected. Consider requiring prepaid payment.
        </div>
      )}
    </div>
  );
}
