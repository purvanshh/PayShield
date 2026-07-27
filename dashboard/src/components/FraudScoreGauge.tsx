interface Props {
  probability: number;
  decision: string;
}

export function FraudScoreGauge({ probability, decision }: Props) {
  const color = probability > 0.85 ? "#dc2626" : probability > 0.5 ? "#f59e0b" : "#16a34a";
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - probability);

  const badgeStyle: Record<string, React.CSSProperties> = {
    BLOCK: { background: "#dc2626", color: "#fff" },
    REVIEW: { background: "#f59e0b", color: "#000" },
    ALLOW: { background: "#16a34a", color: "#fff" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
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
          {(probability * 100).toFixed(0)}%
        </text>
        <text x="80" y="100" textAnchor="middle" fill="#94a3b8" fontSize={12}>
          fraud probability
        </text>
      </svg>
      <span
        style={{
          padding: "4px 16px",
          borderRadius: 20,
          fontWeight: 600,
          fontSize: 13,
          ...(badgeStyle[decision] || {}),
        }}
      >
        {decision}
      </span>
    </div>
  );
}
