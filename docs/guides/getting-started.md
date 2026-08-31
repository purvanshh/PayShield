# Getting Started Guide

## Prerequisites

- Python 3.11 (the canonical stack — a 3.12+ environment will not reproduce the committed numbers)
- Docker & Docker Compose (only for the live-stack demo)
- Redis 7+ (only for the live scorer path)

## Installation

```bash
git clone https://github.com/purvanshh/PayShield.git
cd PayShield
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Configuration

```bash
cp .env.example .env
```

Key variables (see `.env.example` for the full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `PAYSHIELD_DEV_API_KEY` | API key for all endpoints (`x-api-key` header) | `payshield-dev-key-2026` |
| `REDIS_HOST` / `REDIS_PORT` | Redis connection (live scorer path) | `localhost:6379` |
| `ENCRYPTION_KEY` | AES-256 key for data at rest (dev-only default) | `pay-shield-dev-aes256-key-0001` |
| `ENFORCE_RBAC` | Role-gated admin endpoints | `true` in compose |

## Running

### Hermetic (no services — the evaluation path)

The return-risk evidence is fully reproducible with zero services. Use the
canonical Python 3.11 venv (`.venv-verify`) — create it once with
`make setup-verify` — or just run `make verify` for the full 11/11 gate:

```bash
make setup-verify                # creates .venv-verify + installs pinned deps
.venv-verify/bin/python scripts/train_xgb_return_risk.py      # train (~20s)
.venv-verify/bin/python scripts/ablation_study.py             # ablation (~60s)
.venv-verify/bin/python scripts/tune_xgb.py                   # tune (~15s)
.venv-verify/bin/python scripts/benchmark_return_risk.py      # Redis-backed benchmark
.venv-verify/bin/python docs/cost_model/calculator.py         # the numbers in ₹
.venv-verify/bin/python docs/cost_model/calculator.py --vertical-sensitivity
```

### Live stack (Docker)

```bash
docker compose -f docker/docker-compose.yml up -d --build   # api + redis + dashboard
make seed                                                   # seed the curated scenarios
make verify-live                                            # 11 curated checks vs real Redis
```

Health: `curl http://localhost:8000/health`.

## Verify the return-risk scorer

```bash
curl -X POST http://localhost:8000/v1/return/score \
  -H "X-API-Key: payshield-dev-key-2026" -H "Content-Type: application/json" \
  -d '{"order_id":"ORD_DEMO_001","user_id":"U_SERIAL_001","merchant_id":"M_FASHION_001",
       "amount":5500,"category":"fashion","payment_method":"UPI","cod_flag":true}'

# Drift report
curl http://localhost:8000/admin/drift/return-risk -H "X-API-Key: payshield-dev-key-2026"
```

## Next Steps

- [Evaluator Guide](../../EVALUATOR_GUIDE.md) — the 10-minute walkthrough
- [API Reference](../API_REFERENCE.md)
- [Development Guide](development.md)
- [Track 2 Architecture](../TRACK2_ARCHITECTURE.md)