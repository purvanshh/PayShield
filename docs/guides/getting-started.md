# Getting Started Guide

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Redis 7+
- PostgreSQL 16+
- Node.js 20+ (for dashboard)
- Make

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/payshield.git
cd payshield
```

### 2. Environment Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Configuration

```bash
cp .env.example .env
# Edit .env with your settings
```

Required environment variables (see `.env.example` for the full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `PAYSHIELD_DEV_API_KEY` | API key for all endpoints (`x-api-key` header) | `payshield-dev-key-2026` |
| `REDIS_HOST` / `REDIS_PORT` | Redis connection | `localhost:6379` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://payshield:payshield@localhost:5432/payshield` |
| `NEO4J_URI` | Neo4j connection | `bolt://localhost:7687` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Local LLM inference | `http://localhost:11434` / `qwen2.5:3b` |
| `ENCRYPTION_KEY` | AES-256 key for data at rest (PCI-DSS 3.4) | dev-only default |
| `DATA_REGION` | Data residency (RBI DL-1) | `IN` |
| `ENFORCE_RBAC` | Role-gated admin endpoints | `false` locally (compose sets `true`) |

### 4. Database Setup

```bash
# Create database
createdb payshield

# Run migrations
alembic upgrade head

# Seed sample data (optional)
python scripts/seed_data.py
```

### 5. Running the System

#### Using Docker Compose (recommended for development)

```bash
# Pull the LLM image the compose file expects
ollama pull qwen2.5:3b

# Start all 5 services (api, worker, redis, ollama, dashboard)
docker compose -f docker/docker-compose.yml up -d --build
```

Health: `curl http://localhost:8000/health` → `{"status": "healthy", "checks": {redis, neo4j, ollama, celery}}`.

#### Manual Start

```bash
# Terminal 1: API Server
uvicorn api.main:app --reload --port 8000

# Terminal 2: Celery Worker
celery -A tasks.celery_app worker -Q investigation,default -l info

# Terminal 3: Dashboard (optional)
cd dashboard && npm run dev
```

### 6. Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Score a transaction (normal → ALLOW)
curl -X POST http://localhost:8000/v1/score \
  -H "x-api-key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"txn_id":"TEST001","user_id":"U001","merchant_id":"M001","amount":500,
       "timestamp":"2026-07-31T12:00:00","device_fingerprint":"fp_test_1",
       "location":{"lat":19.076,"lon":72.8777,"timestamp":"2026-07-31T12:00:00"},
       "mcc_code":"5411","txn_type":"P2M"}'

# Compliance status
curl http://localhost:8000/admin/compliance/status -H "x-api-key: payshield-dev-key-2026"

# Drift report
curl http://localhost:8000/admin/drift/psi -H "x-api-key: payshield-dev-key-2026"
```

## Next Steps

- [Architecture Overview](../architecture/overview.md)
- [API Documentation](../api/endpoints.md)
- [Development Guide](development.md)
- [Deployment Guide](../operations/deployment.md)
