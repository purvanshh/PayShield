# Troubleshooting Guide

## Common Issues

### 1. API Returns 503 Service Unavailable

**Symptoms:**
- HTTP 503 responses
- `/health` endpoint fails

**Causes & Solutions:**

| Cause | Check | Solution |
|-------|-------|----------|
| Database down | `kubectl exec deploy/postgres-0 -- pg_isready` | Restart postgres StatefulSet |
| Redis down | `redis-cli ping` | Restart Redis deployment |
| OOM killed | `kubectl describe pod` | Increase memory limits |
| Dependency missing | Pod logs show import errors | Rebuild Docker image |

### 2. High Latency on Scoring

**Symptoms:**
- Score API takes >200ms
- p99 latency alert firing

**Checks:**
```bash
# 1. Check model loading time
kubectl exec deploy/payshield-api -- python -c "
from ml.models import load_models
import time; start = time.time()
load_models()
print(f'Model load: {time.time()-start:.2f}s')
"

# 2. Check Redis latency
kubectl exec deploy/redis -- redis-cli --latency -h redis

# 3. Check PostgreSQL query performance
kubectl exec postgres-0 -- psql -c "
SELECT query, calls, total_time/calls as avg_time_ms
FROM pg_stat_statements
ORDER BY total_time DESC LIMIT 10;
"
```

**Solutions:**
- Increase cache TTL for frequent transactions
- Add more API replicas
- Optimize slow database queries
- Consider PostgreSQL read replicas

### 3. Celery Tasks Not Processing

**Symptoms:**
- Queue depth growing
- No workers consuming tasks

**Checks:**
```bash
# 1. Check worker status
kubectl logs deploy/payshield-celery-worker --tail=50

# 2. Check queue depth
kubectl exec deploy/redis -- redis-cli LLEN celery
kubectl exec deploy/redis -- redis-cli LLEN investigations

# 3. Check worker registration
kubectl exec deploy/payshield-celery-worker -- celery -A tasks.celery_app status
```

**Solutions:**
- Scale up workers: `kubectl scale deploy/payshield-celery-worker --replicas=5`
- Restart workers: `kubectl rollout restart deploy/payshield-celery-worker`
- Purge stuck tasks: `kubectl exec deploy/payshield-celery-worker -- celery -A tasks.celery_app purge -f`

### 4. Model Accuracy Degradation

**Symptoms:**
- Decline in fraud detection rate
- Increase in false positives
- Model confidence drifting

**Checks:**
```bash
# 1. Check model metrics
curl localhost:8000/v1/models/metrics

# 2. Compare with baseline
curl localhost:8000/admin/drift/psi -H "X-API-Key: payshield-dev-key-2026"
python scripts/run_drift_report.py

# 3. Check raw feature samples in Redis
redis-cli zcard drift:feat:amount_total_1h
redis-cli zrange drift:feat:amount_total_1h -5 -1 WITHSCORES
```

**Solutions:**
- Trigger retraining: `POST /v1/models/retrain`
- Check data quality in recent transactions
- Rollback to previous model version
- Investigate feature distribution drift (PSI report above)

### 5. Drift Report Shows Absurd PSI Values (e.g. > 10)

**Root cause (fixed 2026-07-31):** the original PSI estimator used 10
fixed-width bins with zero-mass bins and no smoothing. With small, discrete
samples (n ≈ 14), a bin holding mass from only one side produced
`log((p+1e-10)/1e-10) ≈ 23` per bin → PSI 43.4 on genuinely drifty data.
`observability/drift.py` now uses shared quantile bins, bin-count scaling,
and Laplace smoothing — the same data scores 3.86.

**If you still see an outlier PSI today:**
- Confirm both windows have ≥ 3 samples (`expected_samples` / `actual_samples` in the report)
- Confirm the zset convention is `member = "{ts}:{value}"`, `score = timestamp` (writer: `api/routes/score.py:_record_drift_samples`)
- A genuinely non-overlapping distribution (e.g. hourly amount aggregate halved) will legitimately produce PSI > 1 — investigate the business event before tuning thresholds

### 6. Compliance Scores Regressed After A Rebuild

**Symptom:** PCI 10.1 (audit dir) or RBI AI-1/AI-2 (explanations/feedback) findings reappear.

**Cause:** audit logs, feedback, and explanation artifacts are generated at
runtime. A fresh environment starts empty.

**Fix:** drive real traffic (a velocity burst produces BLOCK/REVIEW → explanations
+ audit entries) and submit ≥ 10 analyst feedbacks (`POST /v1/feedback`), then
re-run the checkers:

```bash
docker compose -f docker/docker-compose.yml exec api python3 -c "
from compliance.pci_dss import PCIDSSComplianceChecker
from compliance.rbi_localization import RBILocalizationChecker
print(PCIDSSComplianceChecker().generate_report()['score'])
print(RBILocalizationChecker().generate_report()['score'])
"
```

Note: compose mounts named volumes over the data dirs, so artifacts survive
`docker compose up -d --build` recreations (see `docker/docker-compose.yml`).

### 7. WebSocket Connection Issues

**Symptoms:**
- Clients cannot connect
- Connections dropping frequently

**Checks:**
```bash
# 1. Check WS server pods
kubectl get pods -l app.kubernetes.io/component=ws

# 2. Check logs for errors
kubectl logs deploy/payshield-ws --tail=50 | grep -i error

# 3. Check connection count
kubectl exec deploy/payshield-ws -- python -c "
from api.websocket.manager import ConnectionManager
print(f'Active connections: {len(ConnectionManager().connections)}')
"
```

**Solutions:**
- Increase WS server replicas
- Check SSL certificate validity
- Verify WebSocket service configuration
- Increase connection limits in ingress

### 8. Backup Failure
**Symptoms:**
- Backup CronJob shows errors
- Missing backups in S3

**Checks:**
```bash
# 1. Check backup job status
kubectl get jobs -l app.kubernetes.io/component=backup

# 2. Check backup logs
kubectl logs job/backup-postgres-<id>

# 3. Verify S3 access
aws s3 ls s3://payshield-backups/
```

**Solutions:**
- Verify S3 bucket permissions
- Check PostgreSQL connectivity from backup pod
- Ensure sufficient disk space for backup
- Restart backup CronJob if stuck

## Debugging Tools

### Python Debugging

```bash
# Run interactive Python in pod
kubectl exec -it deploy/payshield-api -- python

# Profile a specific request
kubectl exec deploy/payshield-api -- python -c "
import cProfile
from api.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
cProfile.run('client.post(\"/v1/score\", json={...})')
"
```

### Network Debugging

```bash
# Test internal connectivity
kubectl exec deploy/payshield-api -- curl -v http://redis:6379
kubectl exec deploy/payshield-api -- nc -zv postgres 5432

# DNS resolution test
kubectl exec deploy/payshield-api -- nslookup redis
```

### Database Debugging

```bash
# Direct SQL queries
kubectl exec postgres-0 -- psql -c "SELECT * FROM pg_stat_activity"

# Show slow queries
kubectl exec postgres-0 -- psql -c "
SELECT query, calls, round(total_time::numeric, 2) as total_ms,
       round(mean_time::numeric, 2) as avg_ms
FROM pg_stat_statements
ORDER BY total_time DESC LIMIT 5;"
```

## Performance Tuning

### API Tuning

| Parameter | Default | Production | Description |
|-----------|---------|------------|-------------|
| `workers` | 4 | 8-16 | Gunicorn workers |
| `keepalive` | 5 | 30 | Connection keepalive |
| `max_requests` | 1000 | 5000 | Requests before restart |
| `backlog` | 2048 | 4096 | Connection backlog |

### Database Tuning

| Parameter | Default | Production | Description |
|-----------|---------|------------|-------------|
| `max_connections` | 100 | 200 | Max DB connections |
| `shared_buffers` | 128MB | 1GB | Memory for caching |
| `effective_cache_size` | 4GB | 8GB | Query planner cache |
| `work_mem` | 4MB | 32MB | Per-query memory |
| `maintenance_work_mem` | 64MB | 256MB | Maintenance operations |

### Celery Tuning

| Parameter | Default | Production | Description |
|-----------|---------|------------|-------------|
| `concurrency` | 4 | 8-16 | Worker processes |
| `max_tasks_per_child` | 100 | 1000 | Prevent memory leaks |
| `task_acks_late` | True | True | At-least-once delivery |
| `worker_prefetch_multiplier` | 4 | 1 | Fair task distribution |
