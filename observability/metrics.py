from prometheus_client import Counter, Histogram, Gauge

fraud_score_histogram = Histogram("fraud_score", "Fraud probability distribution", buckets=[0.5, 0.7, 0.85, 0.95, 1.0])
inference_latency = Histogram("inference_latency_seconds", "Inference latency by layer", labelnames=["layer"], buckets=[0.001, 0.005, 0.01, 0.05, 0.1])
layer1_block_rate = Counter("layer1_block_total", "Layer 1 BLOCK decisions")
layer2_escalation_rate = Counter("layer2_escalation_total", "Layer 2 escalations")
llm_queue_depth = Gauge("llm_investigation_queue_depth", "LLM investigation queue depth")
redis_hit_rate = Gauge("redis_feature_store_hit_rate", "Redis feature store cache hit rate")
