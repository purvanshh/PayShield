# Tribal Knowledge — PayShield Operations

## Deployment Quirks

### ArgoCD Sync Timing
- ArgoCD syncs every 3 minutes by default
- If you need immediate sync: `argocd app sync payshield-prod`
- Health checks take ~30s post-sync before marking healthy

### Database Migrations
- Migrations run automatically on deployment via Docker entrypoint
- If migration fails: pod stays in CrashLoopBackOff
- Fix: `kubectl exec deploy/payshield-api -- alembic upgrade head` to debug
- Rollback: `kubectl exec deploy/payshield-api -- alembic downgrade -1`

### Celery Worker Restart
- Workers have a 120s graceful shutdown timeout
- During restart, in-flight tasks complete before shutdown
- If tasks are stuck: `celery -A tasks.celery_app purge -f`

## Known Workarounds

### Redis Memory
- Redis does not have a maxmemory-policy set by default
- If Redis OOM: `kubectl exec deploy/redis -- redis-cli CONFIG SET maxmemory-policy allkeys-lru`
- Add to ConfigMap for persistence

### PostgreSQL Connections
- Default max_connections is 100
- Under load, connections may exhaust
- Workaround: `kubectl exec pod/postgres-0 -- psql -c "ALTER SYSTEM SET max_connections=200;" && kubectl rollout restart statefulset/postgres`

### Model Cache
- Models cache in /tmp with LRU eviction
- After deployment, first ~10 requests may be slow (model loading)
- This is normal — cache warms up within 30 seconds

## Debugging Tips

1. **"It works on my machine"** — Check `kubectl logs` for ConfigMap differences
2. **"The model is wrong"** — Check `models/production/current.pt` symlink target
3. **"Alerts are too noisy"** — Check Alertmanager silences, adjust in `sre/slos/`
4. **"Backups are failing"** — Check S3 bucket permissions and IAM role

## Who Knows What

| Area | Primary | Secondary |
|------|---------|-----------|
| Model Training | ML Engineer | Data Engineer |
| K8s Deployments | DevOps Lead | SRE |
| Database Schema | Backend Lead | Data Engineer |
| Agent System | ML Engineer | Backend Lead |
| Compliance | Security Lead | DevOps Lead |
| Dashboard | Frontend Lead | Full-stack Dev |
