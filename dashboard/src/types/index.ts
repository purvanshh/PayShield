export interface ScoreRequest {
  txn_id: string;
  user_id: string;
  merchant_id: string;
  amount: number;
  timestamp: string;
  device_fingerprint: string;
  location?: { lat: number; lon: number };
  mcc_code?: string;
  txn_type: "P2P" | "P2M" | "COLLECT";
}

export interface FraudScoreResponse {
  txn_id: string;
  decision: "ALLOW" | "BLOCK" | "REVIEW";
  fraud_probability: number;
  layer_triggered: "L1_STATISTICAL" | "L2_GNN" | "ENSEMBLE";
  evidence: Record<string, unknown>;
  latency_ms: number;
  model_version: string;
}

export interface InvestigationReport {
  txn_id: string;
  narrative: string;
  fraud_type: "MULE_RING" | "BURST_ATTACK" | "MERCHANT_COLLUSION" | "ACCOUNT_TAKEOVER" | "OTHER";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  recommended_action: string;
  key_evidence: string[];
  reasoning: string;
  generated_at: string;
  model_version?: string;
}

export interface FeedbackRequest {
  txn_id: string;
  analyst_id: string;
  original_decision: string;
  analyst_decision: string;
  reason?: string;
  category: "FALSE_POSITIVE" | "FALSE_NEGATIVE" | "TRUE_POSITIVE" | "TRUE_NEGATIVE";
}

export interface AlertPayload {
  txn_id: string;
  fraud_probability: number;
  decision: string;
  fraud_type: string;
  narrative_preview: string;
  timestamp: string;
  priority: number;
}

export interface HealthCheck {
  status: string;
  checks: Record<string, string>;
}

export interface ApiError {
  message: string;
  status: number;
  code: string;
}
