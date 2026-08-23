# API Reference

## Base URL

- Development: `http://localhost:8000`
- Production: `https://api.payshield.io`

## Authentication

All endpoints (except `/health*` and `/metrics`) require an API key:

```
x-api-key: payshield-dev-key-2026
```

or a JWT Bearer token:

```
Authorization: Bearer <access_token>
```

Role-scoped endpoints (`Admin`, `Feedback`, RBAC-gated) additionally check
permissions from `configs/rbac.yaml`. Roles: `system`, `analyst`, `admin`.

Rate limits: per-API-key 1000 req/hr, per-user 1000 req/hr. Response:
`429 Too Many Requests` with `Retry-After` header.

Interactive docs: `http://localhost:8000/docs` (Swagger) · `/redoc` (ReDoc).

## Authentication

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/auth/login` | Login with username/password → JWT access + refresh |
| `POST` | `/v1/auth/refresh` | Rotate refresh token (7-day sliding window, old token revoked) |
| `POST` | `/v1/auth/totp/setup` | Provision TOTP secret for admin account (requires admin JWT) |
| `POST` | `/v1/auth/totp/verify` | Verify TOTP code (enables 2FA on success, requires admin JWT) |

## Fraud Scoring

### Score a single transaction

```
POST /v1/score
```

Request:

```json
{
  "txn_id": "CMP_B2_8",
  "user_id": "u_burst_02",
  "merchant_id": "m_burst_02",
  "amount": 95000.0,
  "timestamp": "2026-07-31T10:30:38",
  "device_fingerprint": "fp_burst_99",
  "location": {"lat": 19.076, "lon": 72.8777, "timestamp": "2026-07-31T10:30:38"},
  "mcc_code": "6011",
  "txn_type": "P2M"
}
```

`txn_type` is one of `P2P` | `P2M` | `COLLECT`. Features (velocity, geo,
Benford) are computed live from Redis history; a velocity burst or geo jump
produces `BLOCK`/`REVIEW` via Layer 1 rules.

Response:

```json
{
  "txn_id": "CMP_B2_8",
  "decision": "REVIEW",
  "fraud_probability": 0.0,
  "layer_triggered": "ENSEMBLE",
  "evidence": {
    "triggered_rules": ["V-RULE-03"],
    "ensemble_confidence": 0.0,
    "latency_breakdown": {"l1_rules_ms": 0.11, "ensemble_ms": 0.02}
  },
  "latency_ms": 12.4,
  "model_version": "1.0.0"
}
```

`decision` is one of `ALLOW` | `BLOCK` | `REVIEW`. `BLOCK`/`REVIEW`
transactions enqueue an async LLM investigation, append a tamper-evident
audit entry, and persist an explanation artifact.

### Batch score

```
POST /v1/batch
```

Body: `{"transactions": [<ScoreRequest>, ...]}` (max 100). Response:
`{"results": [<FraudScoreResponse>], "batch_latency_ms": ...}`.

## Investigations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/investigation/{txn_id}` | LLM investigation report (generated async; accepts flat or nested report) |
| `GET` | `/v1/investigations` | List investigations (paginated) |

Investigation status is `queued` → `success`; reports are served from
`investigation:{txn_id}` in Redis. On CPU (qwen2.5:3b via Ollama) generation
takes ~35 s — it never blocks `/v1/score`.

## Feedback Loop

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/feedback` | API Key + RBAC | Submit analyst decision; persisted to `store/feedback/` and Redis, notifies HumanReviewAgent |
| `GET` | `/v1/feedback/stats` | API Key + RBAC | Feedback volume by category |

```json
POST /v1/feedback
{
  "txn_id": "CMP_F2_1",
  "analyst_id": "analyst_priya",
  "original_decision": "REVIEW",
  "analyst_decision": "ALLOW",
  "reason": "burst matches verified merchant payout schedule",
  "category": "FALSE_POSITIVE"
}
```

## Graph Analysis

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/graph/investigate` | Investigate entity in fraud graph |
| `GET` | `/v1/graph/network/{entity_id}` | Entity ego-graph |
| `POST` | `/v1/graph/entity` | Create graph entity |
| `POST` | `/v1/graph/link` | Link two entities |
| `GET` | `/v1/graph/risk-paths` | Risk paths between entities |
| `GET` | `/v1/graph/stats` | Graph DB statistics |

## Compliance & Sanctions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/compliance/status` | PCI-DSS, RBI, EU AI Act scores |
| `GET` | `/admin/compliance/check/{user_id}` | Sanctions + KYC combined check |
| `POST` | `/admin/compliance/sanctions/check` | OFAC/UN sanctions screening |
| `GET` | `/admin/compliance/kyc/{user_id}` | KYC tier verification |
| `POST` | `/admin/compliance/aml/check` | AML velocity + structuring check |
| `POST` | `/admin/compliance/report` | Generate quarterly compliance report |
| `POST` | `/admin/compliance/report/{framework}` | Framework-specific report |
| `GET` | `/admin/compliance/evidence` | List compliance evidence archives |
| `POST` | `/admin/compliance/evidence/collect` | Trigger evidence collection |

Current scores (2026-08-24): **PCI-DSS 90/100** (passed), **RBI 83/100**
(passing) — see `COMPLIANCE_DELTA.md` / `COMPLIANCE_DELTA_TRACK2.md`.

## Admin & Operations

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/admin/rules/reload` | API Key + RBAC | Reload statistical rules from YAML |
| `POST` | `/admin/models/promote` | API Key + RBAC | Promote model version |
| `POST` | `/admin/config/threshold` | API Key + RBAC | Update scoring threshold |
| `GET` | `/admin/config` | API Key + RBAC | View all configurations |
| `GET` | `/admin/agents/health` | API Key + RBAC | Multi-agent health status |
| `POST` | `/admin/agents/{id}/restart` | API Key + RBAC | Restart a specific agent |
| `GET` | `/admin/drift/psi` | API Key + RBAC | PSI drift report (yesterday vs today) |

### Drift report example

```
GET /admin/drift/psi
```

```json
{
  "generated_at": "2026-07-31T16:05:15Z",
  "method": "PSI — shared quantile bins (scaled to sample size) + Laplace smoothing",
  "threshold": {"stable": 0.1, "drift": 0.25},
  "features": {
    "amount_total_1h": {"psi": 3.8608, "status": "DRIFT", "n_bins": 3,
                        "expected_samples": 13, "actual_samples": 14}
  },
  "drifted_features": ["amount_total_1h"],
  "status": "DRIFT_DETECTED"
}
```

## A/B Experiments

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/experiments` | Register new A/B experiment |
| `GET` | `/admin/experiments` | List all experiments |
| `GET` | `/admin/experiments/{id}/results` | Results + p-value |
| `POST` | `/admin/experiments/{id}/promote` | Promote challenger model |
| `POST` | `/admin/experiments/{id}/rollback` | Rollback to champion |

## Real-Time Streams

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `WS` | `/v1/stream` | Token/Key | WebSocket live fraud alerts |
| `GET` | `/v1/stream/sse` | Token | Server-Sent Events stream |

## Health & Metrics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Full health: Redis, Neo4j, Ollama, Celery |
| `GET` | `/health/live` | None | Liveness probe |
| `GET` | `/health/ready` | None | Readiness probe |
| `GET` | `/metrics` | None | Prometheus metrics |

## Error Responses

```json
{
  "error": "VALIDATION_ERROR",
  "detail": [{"type": "missing", "loc": ["header", "x-api-key"], "msg": "Field required"}],
  "request_id": "c95b4e9a-e230-45bb-b66b-8d01348bcd1c"
}
```

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `Missing authentication credentials` | 401 | No API key / bearer token |
| `Permission denied` | 403 | Key valid, role lacks permission |
| `BatchSizeExceededError` | 400 | > 100 transactions in batch |
| `Transaction ... not found` | 404 | Investigation/feedback target missing |
