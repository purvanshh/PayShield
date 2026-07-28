# PayShield Disaster Recovery Runbook

## Recovery Objectives

| Tier | Metric | Target |
|------|--------|--------|
| RPO | Recovery Point Objective | 1 hour |
| RTO | Recovery Time Objective | 15 minutes |
| MTO | Maximum Tolerable Outage | 1 hour |

## Recovery Tiers

### Tier 1: Critical (RTO < 1 min)
- API health check failure
- Redis cache failure
- Zero pods running

### Tier 2: High (RTO < 5 min)
- PostgreSQL primary failure
- Celery worker starvation
- High error rate (>5%)

### Tier 3: Medium (RTO < 30 min)
- Model accuracy degradation
- LLM investigator failure
- WebSocket connection issues

---

## Runbook 1: Complete Application Failure

### Detection
- Prometheus alert: `PayshieldAllPodsDown`
- Grafana dashboard shows 0 running pods
- External monitoring reports 503 errors

### Recovery Steps

1. **Verify cluster health**
   ```bash
   kubectl cluster-info
   kubectl get nodes -o wide
   kubectl get pods -n payshield
   ```

2. **Check deployments**
   ```bash
   kubectl -n payshield get deployments
   kubectl -n payshield describe deployment/payshield-api
   ```

3. **Force restart if needed**
   ```bash
   kubectl -n payshield rollout restart deployment/payshield-api
   kubectl -n payshield rollout status deployment/payshield-api --timeout=180s
   ```

4. **Verify recovery**
   ```bash
   curl -f http://payshield-api:8000/health
   curl -f http://payshield-api:8000/ready
   ```

### Post-Recovery
- [ ] Confirm all pods are healthy
- [ ] Verify database connectivity
- [ ] Check alertmanager for residual alerts
- [ ] Root cause analysis

---

## Runbook 2: PostgreSQL Failure

### Detection
- Alert: `PayshieldPostgresDown`
- API errors: `could not connect to server`
- pg_isready fails

### Recovery Steps

1. **Check pod status**
   ```bash
   kubectl -n payshield get pods -l app.kubernetes.io/component=postgres
   kubectl -n payshield describe pod/postgres-0
   ```

2. **Check logs**
   ```bash
   kubectl -n payshield logs postgres-0 --tail=100
   ```

3. **Restore from latest backup** (if data corruption)
   ```bash
   # Find latest backup
   aws s3 ls s3://payshield-backups/postgres/ | sort | tail -5

   # Run restore
   ./dr/restore-postgres.sh s3://payshield-backups/postgres/payshield_pg_latest.dump
   ```

4. **If volume is corrupted, restore from snapshot**
   ```bash
   # List EBS snapshots
   aws ec2 describe-snapshots --filters Name=tag:Name,Values=payshield-postgres

   # Create volume from snapshot and attach (follow cloud provider docs)
   ```

### Verification
```bash
kubectl -n payshield exec postgres-0 -- pg_isready -U payshield
kubectl -n payshield exec deployment/payshield-api -- python -c "from api.database import check_connection; print(check_connection())"
```

---

## Runbook 3: Redis Cache Failure

### Detection
- Alert: `PayshieldRedisDown`
- High latency on cache operations
- Celery task failures

### Recovery Steps

1. **Verify Redis status**
   ```bash
   kubectl -n payshield get pods -l app.kubernetes.io/component=redis
   kubectl -n payshield logs -l app.kubernetes.io/component=redis --tail=50
   ```

2. **Restart Redis**
   ```bash
   kubectl -n payshield rollout restart deployment redis
   kubectl -n payshield rollout status deployment redis --timeout=120s
   ```

3. **Restore from RDB backup** (if needed)
   ```bash
   ./dr/restore-redis.sh s3://payshield-backups/redis/payshield_redis_latest.rdb
   ```

### Warm-Up Cache
After restore, cache will be cold. Monitor hit rate:
```bash
kubectl -n payshield exec deployment/redis -- redis-cli INFO stats | grep hits
```

---

## Runbook 4: Celery Worker Starvation

### Detection
- Alert: `PayshieldCeleryQueueGrowth`
- Queue depth exceeds 10,000
- Processing latency > 30 seconds

### Recovery Steps

1. **Inspect queues**
   ```bash
   kubectl -n payshield exec deployment/redis -- redis-cli LLEN celery
   kubectl -n payshield exec deployment/redis -- redis-cli LRANGE celery 0 10
   ```

2. **Scale workers**
   ```bash
   kubectl -n payshield scale deployment/payshield-celery-worker --replicas=10
   ```

3. **Check for stuck tasks**
   ```bash
   kubectl -n payshield logs -l app.kubernetes.io/component=celery-worker --tail=50 | grep -i error
   ```

4. **Purge queue** (if tasks are poisoned)
   ```bash
   kubectl -n payshield exec deployment/payshield-celery-worker -- celery -A tasks.celery_app purge -f
   ```

---

## Runbook 5: Infrastructure/Cloud Failure

### Detection
- Multiple AZs affected
- Cluster node failures
- Cloud provider incident

### Recovery Steps

1. **Failover to secondary region**
   ```bash
   # Switch kubectl context
   kubectl config use-context payshield-dr

   # Deploy from backup
   ./scripts/deploy_k8s.sh prod dr-cluster
   ```

2. **Restore database**
   ```bash
   ./dr/restore-postgres.sh s3://payshield-backups/postgres/payshield_pg_latest.dump
   ./dr/restore-redis.sh s3://payshield-backups/redis/payshield_redis_latest.rdb
   ```

3. **Update DNS**
   ```bash
   # Point payshield.io to DR cluster IP
   kubectl -n payshield-prod get ingress payshield-ingress
   ```

4. **Verify full functionality**
   ```bash
   ./scripts/test-restore.sh
   ```

---

## Automated Recovery Procedures

### Self-Healing
- Kubernetes automatically restarts failed containers
- HPA adjusts replica count based on load
- PodDisruptionBudgets ensure minimum availability

### Backup Schedule

| Component | Frequency | Retention | Method |
|-----------|-----------|-----------|--------|
| PostgreSQL | Every 6 hours | 30 days | pg_dump (custom format) |
| Redis | Every 24 hours | 7 days | RDB snapshot |
| Configuration | Every 24 hours | 90 days | tar.gz archive |

### Backup Validation
- [ ] Hourly: backup file existence check
- [ ] Daily: backup restore test on staging
- [ ] Weekly: full DR drill with RTO/RPO verification

---

## Communication Plan

### Severity Levels

| Level | Description | Response Time | Notify |
|-------|-------------|---------------|--------|
| SEV-1 | Complete outage | 5 min | All engineers + management |
| SEV-2 | Partial degradation | 15 min | On-call + team lead |
| SEV-3 | Non-critical issue | 1 hour | On-call engineer |

### Escalation Contacts

| Role | Name | Contact |
|------|------|---------|
| Primary On-Call | Rotation A | oncall@payshield.io |
| Secondary On-Call | Rotation B | oncall-backup@payshield.io |
| Engineering Lead | Lead Engineer | eng-lead@payshield.io |
| DevOps Lead | DevOps Engineer | devops@payshield.io |
| Management | VP Engineering | vp-eng@payshield.io |

### Post-Incident Process

1. **Immediate** - resolve the issue
2. **30 min post-resolution** - send initial incident summary
3. **24 hours** - conduct root cause analysis
4. **72 hours** - complete incident report with action items
5. **1 week** - implement preventive measures

---

## Testing & Validation

### Monthly DR Drill Procedure

1. **Scheduled maintenance window**: Sunday 02:00-04:00
2. **Scope**: Full PostgreSQL restore on staging
3. **Steps**:
   ```bash
   # Step 1: Take fresh production backup
   ./dr/backup-postgres.sh

   # Step 2: Restore to staging
   PGHOST=staging-postgres ./dr/restore-postgres.sh s3://payshield-backups/postgres/latest.dump

   # Step 3: Run validation queries
   psql -h staging-postgres -U payshield -d payshield -f dr/validate-restore.sql

   # Step 4: Document results
   ./dr/test-restore.sh
   ```

### Validation Queries
```sql
-- dr/validate-restore.sql
SELECT 'Row count check:' as check_name;
SELECT 'transactions', COUNT(*) FROM transactions;
SELECT 'rules', COUNT(*) FROM rules;
SELECT 'models', COUNT(*) FROM models;
SELECT 'investigations', COUNT(*) FROM investigations;

SELECT 'Integrity check:' as check_name;
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
```
