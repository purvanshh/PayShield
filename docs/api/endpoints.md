# API Reference

## Base URL
- Development: `http://localhost:8000`
- Production: `https://api.payshield.io`

## Authentication

All endpoints (except health) require JWT Bearer token:

```
Authorization: Bearer <token>
```

### Get Token
```
POST /auth/token
{
  "client_id": "string",
  "client_secret": "string"
}
```

## Endpoints

### Health & Readiness

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe |

### Transaction Scoring

#### Score Single Transaction
```
POST /v1/score

Request:
{
  "transaction_id": "txn_001",
  "amount": 299.99,
  "currency": "USD",
  "timestamp": "2026-07-28T12:00:00Z",
  "merchant": {
    "id": "merchant_123",
    "category": "electronics",
    "country": "US"
  },
  "user": {
    "id": "user_456",
    "email": "user@example.com"
  },
  "device": {
    "fingerprint": "abc123",
    "ip": "203.0.113.1",
    "user_agent": "Mozilla/5.0..."
  }
}

Response:
{
  "transaction_id": "txn_001",
  "score": 0.87,
  "decision": "investigate",
  "confidence": 0.87,
  "processing_time_ms": 45,
  "model_breakdown": {
    "xgboost": 0.85,
    "lightgbm": 0.88,
    "catboost": 0.82,
    "random_forest": 0.79,
    "mlp": 0.91
  },
  "explanation": "High amount for user profile, new device detected"
}
```

#### Batch Score
```
POST /v1/score/batch

Request: [<transaction>, <transaction>, ...]
Response: [<score_result>, <score_result>, ...]
```

#### Score via WebSocket
```
Connect to ws://localhost:8765/v1/ws/score
Message: <transaction JSON>
Response: <score result JSON>
```

### Investigations

#### List Investigations
```
GET /v1/investigations?page=1&page_size=20&status=pending
```

#### Get Investigation
```
GET /v1/investigations/{id}
```

#### Review Investigation
```
POST /v1/investigations/{id}/review
{
  "decision": "approve" | "decline" | "manual_review",
  "notes": "string"
}
```

### Feedback

#### Submit Feedback
```
POST /v1/feedback
{
  "transaction_id": "txn_001",
  "actual_outcome": "fraud" | "legitimate",
  "correct_decision": "approve" | "decline",
  "notes": "string"
}
```

### Rules

#### List Rules
```
GET /v1/rules
```

#### Create Rule
```
POST /v1/rules
{
  "name": "High Amount Rule",
  "condition": "amount > 10000",
  "action": "block",
  "priority": 10,
  "enabled": true
}
```

#### Update Rule
```
PUT /v1/rules/{id}
```

#### Delete Rule
```
DELETE /v1/rules/{id}
```

### Models

#### List Models
```
GET /v1/models
```

#### Get Model Metrics
```
GET /v1/models/{name}/metrics
```

#### Trigger Retraining
```
POST /v1/models/retrain
```

### Metrics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/metrics` | Prometheus metrics |
| GET | `/v1/metrics/summary` | Summary statistics |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/admin/config` | Current configuration |
| PUT | `/v1/admin/config` | Update configuration |
| GET | `/v1/admin/health/components` | Component health |

## Error Responses

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 30 seconds.",
    "details": {}
  }
}
```

### Error Codes
| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Validation error |
| `UNAUTHORIZED` | 401 | Invalid/expired token |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily down |
| `ENSEMBLE_FAILURE` | 500 | Model inference failed |
