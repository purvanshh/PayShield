import React from "react";

interface Props {
  narrative: string;
  fraudType: string;
  confidence: number;
  recommendedAction: string;
}

export const InvestigationCard: React.FC<Props> = ({
  narrative,
  fraudType,
  confidence,
  recommendedAction,
}) => {
  return (
    <div className="investigation-card">
      <p>{narrative}</p>
      <p>Type: {fraudType}</p>
      <p>Confidence: {(confidence * 100).toFixed(1)}%</p>
      <p>Action: {recommendedAction}</p>
    </div>
  );
};
