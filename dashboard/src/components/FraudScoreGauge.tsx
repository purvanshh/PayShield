import React from "react";

interface Props {
  score: number;
}

export const FraudScoreGauge: React.FC<Props> = ({ score }) => {
  const color = score > 0.85 ? "red" : score > 0.5 ? "orange" : "green";
  return (
    <div style={{ color }}>
      <h2>Fraud Score</h2>
      <div style={{ fontSize: "2em" }}>{(score * 100).toFixed(1)}%</div>
    </div>
  );
};
