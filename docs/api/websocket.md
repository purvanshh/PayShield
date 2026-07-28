# WebSocket API

## Connection

```
ws://localhost:8765/v1/ws/score
wss://api.payshield.io/v1/ws/score
```

Authentication via query parameter:
```
ws://localhost:8765/v1/ws/score?token=<jwt_token>
```

## Message Protocol

### Client → Server

```json
{
  "type": "score_request",
  "id": "msg_001",
  "payload": {
    "transaction_id": "txn_001",
    "amount": 299.99,
    "currency": "USD",
    "merchant": { "id": "m_123", "category": "electronics" },
    "user": { "id": "u_456" },
    "device": { "fingerprint": "abc123", "ip": "203.0.113.1" }
  }
}
```

### Server → Client

```json
{
  "type": "score_result",
  "id": "msg_001",
  "payload": {
    "transaction_id": "txn_001",
    "score": 0.87,
    "decision": "investigate",
    "processing_time_ms": 45
  }
}
```

### Server → Client (Investigation Update)

```json
{
  "type": "investigation_update",
  "id": "inv_001",
  "payload": {
    "transaction_id": "txn_001",
    "stage": "agent_orchestration",
    "progress": 75,
    "current_agent": "network_agent",
    "result": null
  }
}
```

## Flow

1. Client connects with JWT token
2. Client sends `score_request` messages
3. Server responds with `score_result`
4. For borderline cases, server sends `investigation_update`
5. Server sends `investigation_result` when investigation completes

## Rate Limits

- 60 messages per minute per connection
- 10 concurrent connections per client
- Max message size: 1MB

## Error Handling

If a message fails validation, server returns:
```json
{
  "type": "error",
  "id": "msg_001",
  "payload": {
    "code": "INVALID_PAYLOAD",
    "message": "Missing required field: amount"
  }
}
```
