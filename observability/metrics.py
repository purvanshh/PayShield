from prometheus_client import Counter, Histogram, Gauge

fraud_score_histogram = Histogram("fraud_score", "Fraud probability distribution", buckets=[0.5, 0.7, 0.85, 0.95, 1.0])
inference_latency = Histogram("inference_latency_seconds", "Inference latency by layer", labelnames=["layer"], buckets=[0.001, 0.005, 0.01, 0.05, 0.1])
layer1_block_rate = Counter("layer1_block_total", "Layer 1 BLOCK decisions")
layer2_escalation_rate = Counter("layer2_escalation_total", "Layer 2 escalations")
llm_queue_depth = Gauge("llm_investigation_queue_depth", "LLM investigation queue depth")
redis_hit_rate = Gauge("redis_feature_store_hit_rate", "Redis feature store cache hit rate")
chargeback_counter = Counter("chargeback_responses_total", "Chargeback rebuttal generation attempts")
chargeback_submitted = Counter("chargeback_submitted_total", "Chargeback rebuttals submitted to Razorpay")
chargeback_latency = Histogram("chargeback_latency_seconds", "Chargeback response generation latency", buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5])
return_risk_counter = Counter("return_risk_scores_total", "Return-risk scoring requests")
return_risk_latency = Histogram("return_risk_latency_seconds", "Return-risk scoring latency", buckets=[0.005, 0.01, 0.025, 0.05, 0.1])
