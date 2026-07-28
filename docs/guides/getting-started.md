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

Required environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://payshield:payshield@localhost:5432/payshield` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT signing key | (required) |
| `LLM_API_KEY` | OpenAI-compatible API key | (optional) |
| `SENTRY_DSN` | Sentry error tracking | (optional) |

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
make dev
```

#### Manual Start

```bash
# Terminal 1: API Server
uvicorn api.main:app --reload --port 8000

# Terminal 2: Celery Worker
celery -A tasks.celery_app worker -l info -Q default,investigations,training

# Terminal 3: WebSocket Server
python api/ws_server.py

# Terminal 4: Dashboard (optional)
cd dashboard && npm run dev
```

### 6. Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Quick test
python scripts/quick_test.py
```

## Next Steps

- [Architecture Overview](../architecture/overview.md)
- [API Documentation](../api/endpoints.md)
- [Development Guide](development.md)
- [Deployment Guide](../operations/deployment.md)
