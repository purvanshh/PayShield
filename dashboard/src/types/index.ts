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
  fraud_type: "MULE_RING" | "BURST_ATTACK" | "MERCHANT_COLLUSION" | "ACCOUNT_TAKEOVER" | "RETURN_RISK" | "OTHER";
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

export interface FeatureContribution {
  value: number | string | boolean;
  weight: number;
  contribution: number;
  normalized_value?: number | null;
  source?: string;
}

export interface RuleTrigger {
  rule_id: string;
  name: string;
  condition?: string;
  triggered: boolean;
  action?: string;
  severity?: number;
  description?: string;
}

export interface ReturnScoreData {
  order_id: string;
  return_risk_score: number;
  risk_tier: "LOW" | "MEDIUM" | "HIGH";
  confidence: number;
  feature_breakdown: Record<string, FeatureContribution>;
  rules_triggered: RuleTrigger[];
  recommendations: string[];
  user_profile: {
    total_orders: number;
    total_returns: number;
    return_rate_30d: number;
    serial_returner: boolean;
    is_new_user: boolean;
    [key: string]: unknown;
  };
}

export interface AuditTrailEntry {
  timestamp: string;
  action: string;
  agent: string;
  detail?: string;
}

export interface ChargebackRespondData {
  rebuttal_id: string;
  dispute_id: string;
  response_type: "ACCEPT" | "REJECT" | "PARTIAL";
  confidence_score: number;
  evidence_completeness: number;
  narrative: {
    summary: string;
    full_report: string;
    key_evidence: string[];
    quality_score: number;
  };
  razorpay_payload: Record<string, unknown>;
  audit_trail: AuditTrailEntry[];
  warnings: string[];
}
