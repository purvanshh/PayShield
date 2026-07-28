# Operations Manual

## Deployment Architecture

```
┌──────────────────┐
│   ArgoCD (GitOps)│
└────────┬─────────┘
         │ syncs
┌────────┴─────────┐
│   Kubernetes     │
│  ┌───────────┐   │
│  │ Namespace │   │
│  │ payshield │   │
│  └───────────┘   │
└──────────────────┘
```

## Environment Overview

| Environment | Cluster | Namespace | Replicas | Purpose |
|-------------|---------|-----------|----------|---------|
| Dev | dev-cluster | payshield | 1-2 | Development |
| Staging | staging-cluster | payshield-staging | 2-3 | Pre-prod validation |
| Production | prod-cluster | payshield-prod | 3-20 | Production |

## Deployment Process

### Automated (CI/CD)

```bash
# Trigger deployment via GitHub Actions
git push origin main  # → auto-deploys to staging
git tag v1.0.0        # → auto-deploys to production
```

### Manual (Hotfix)

```bash
# Build and push image
docker build -t payshield/api:hotfix-001 .
docker push payshield/api:hotfix-001

# Update deployment
kubectl set image deployment/payshield-api api=payshield/api:hotfix-001 -n payshield-prod

# Monitor rollout
kubectl rollout status deployment/payshield-api -n payshield-prod
```

### ArgoCD Sync

```bash
# Sync specific application
argocd app sync payshield-prod

# Sync with prune
argocd app sync payshield-prod --prune

# Automated sync (self-heal)
argocd app set payshield-prod --sync-policy automated
```

## Scaling

### Horizontal Scaling

```bash
# Manual scale
kubectl scale deployment/payshield-api --replicas=10 -n payshield-prod

# HPA configuration (auto)
kubectl get hpa -n payshield-prod
```

### Vertical Scaling

```bash
# Update resource limits
kubectl edit deployment/payshield-api -n payshield-prod

# Apply VPA recommendation
kubectl apply -f k8s/overlays/prod/vpa.yaml
```

## Monitoring

### Key Metrics

| Metric | Alert Threshold | Severity |
|--------|----------------|----------|
| API Latency (p99) | > 500ms | Warning |
| Error Rate | > 1% | Critical |
| Queue Depth | > 10,000 | Warning |
| CPU Usage | > 80% | Warning |
| Memory Usage | > 85% | Critical |

### Accessing Dashboards

```bash
# Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090

# Grafana (default admin/admin)
kubectl port-forward -n monitoring svc/grafana 3000
```

### Logs

```bash
# Tail API logs
kubectl logs -n payshield -l app.kubernetes.io/component=api -f

# Search logs
kubectl logs -n payshield -l app.kubernetes.io/component=api --tail=100 | grep ERROR

# Loki-powered log search (if deployed)
kubectl port-forward -n monitoring svc/loki 3100
```

## Maintenance

### Database Migrations

```bash
# Run pending migrations
kubectl exec -n payshield deployment/payshield-api -- alembic upgrade head

# Rollback
kubectl exec -n payshield deployment/payshield-api -- alembic downgrade -1

# View history
kubectl exec -n payshield deployment/payshield-api -- alembic history
```

### Backup & Restore

```bash
# Manual backup
./dr/backup-postgres.sh
./dr/backup-redis.sh

# Manual restore
./dr/restore-postgres.sh s3://payshield-backups/postgres/latest.dump
./dr/restore-redis.sh s3://payshield-backups/redis/latest.rdb
```

### Certificate Rotation

```bash
# Check certificate expiry
kubectl get certificate -n payshield-prod

# Force renewal
kubectl delete certificate payshield-tls -n payshield-prod
# Cert-manager will auto-renew
```

## Troubleshooting

### Pod CrashLoopBackOff

```bash
# Check logs
kubectl logs -n payshield deployment/payshield-api --previous

# Describe pod for events
kubectl describe pod -n payshield -l app.kubernetes.io/component=api

# Check resource limits
kubectl top pod -n payshield
```

### Database Connection Issues

```bash
# Test connectivity
kubectl exec -n payshield deploy/payshield-api -- pg_isready

# Check connection pool
kubectl exec -n payshield deploy/payshield-api -- python -c "
from api.database import SessionLocal
with SessionLocal() as session:
    session.execute(text('SELECT 1'))
    print('Database connected')
"
```

### High Latency

```bash
# Check API response times
kubectl exec -n payshield deploy/payshield-api -- curl -w '%{time_total}' localhost:8000/health

# Check Redis latency
kubectl exec -n payshield deploy/redis -- redis-cli --latency

# Check PostgreSQL slow queries
kubectl exec -n payshield pod/postgres-0 -- psql -c "SELECT * FROM pg_stat_activity WHERE state = 'active'"
```

## Security Procedures

### Secret Rotation

```bash
# Rotate JWT secret
kubectl create secret generic jwt-secret --from-literal=SECRET_KEY=$(openssl rand -base64 32) --dry-run=client -o yaml | kubeseal > k8s/base/payshield-sealed-secret.yaml
kubectl rollout restart deployment/payshield-api -n payshield-prod
```

### Access Review
- Review kubectl access quarterly
- Rotate service account tokens every 90 days
- Audit API access logs weekly
- Conduct penetration testing quarterly
