# PayShield Cost Optimization Analysis

## Monthly Cost Breakdown (Estimated)

| Component | Current Cost | Optimized Cost | Savings |
|-----------|-------------|----------------|---------|
| API Pods (3 x m5.large) | $520 | $320 (spot) | $200 |
| Celery Workers (2 x c5.xlarge) | $280 | $140 (spot) | $140 |
| Redis (cache.r5.large) | $160 | $96 (r6g.large reserved) | $64 |
| PostgreSQL (db.r5.xlarge) | $350 | $250 (serverless v2) | $100 |
| Load Balancer | $20 | $20 | $0 |
| EBS Volumes (100GB gp3) | $10 | $8 (reduce gp2→gp3) | $2 |
| Data Transfer | $50 | $40 (compression) | $10 |
| **Total** | **$1,390** | **$874** | **$516 (37%)** |

---

## Optimization Strategies

### 1. Compute Optimization

#### Strategy 1A: Spot Instances for Celery Workers
- Celery workers are fault-tolerant and ideal for spot instances
- Estimated savings: 60-70% vs on-demand
- Implementation: Spot fleet with fallback to on-demand
- Migration plan:
  1. Convert Celery deployment to use spot instances
  2. Configure PodDisruptionBudget to handle interruptions
  3. Implement graceful shutdown handlers in Celery worker

#### Strategy 1B: Right-Sizing Analysis
- Current API pods request 500m CPU / 512Mi memory
- CloudWatch metrics show average usage: 120m CPU / 340Mi memory
- Recommendation: Reduce requests to 250m CPU / 384Mi memory
- Savings: ~$60/month per 3-replica deployment

### 2. Database Optimization

#### Strategy 2A: PostgreSQL to Aurora Serverless v2
- Auto-scales based on load (0.5-128 ACU)
- No need to provision for peak
- Pay only for consumed capacity
- Savings: 30-50% during low-traffic periods

#### Strategy 2B: Read Replicas for Analytics
- Offload reporting queries to read replicas
- Primary instance stays responsive for transactions
- Cost: ~$100/month per replica

### 3. Caching Optimization

#### Strategy 3A: Redis Memory Management
- Current: 13GB allocated, 4.2GB used
- Recommendation: Reduce to 6GB (r6g.large)
- Set maxmemory-policy: allkeys-lru
- Enable active defragmentation

#### Strategy 3B: Local Cache Layer
- Implement in-memory cache (TTL: 60s) before Redis
- Reduces Redis calls by ~40%
- Configuration:
  - `CACHE_TTL_SECONDS=60`
  - `LOCAL_CACHE_SIZE=1000`

### 4. Storage Optimization

#### Strategy 4A: EBS gp3 Migration
- gp3 is 20% cheaper than gp2 with better baseline performance
- Current: 100GB gp2 → Target: 100GB gp3
- Savings: ~$2/month

#### Strategy 4B: Log Lifecycle Management
- Implement log rotation and archival
- Hot (7 days): Fast storage
- Warm (30 days): S3 Standard
- Cold (1 year): S3 Glacier
- Savings: ~$15/month

### 5. Network Optimization

#### Strategy 5A: Data Compression
- Enable gzip compression on API responses
- Reduce Data Transfer by 40-60%
- Implementation: Add to FastAPI middleware

#### Strategy 5B: Connection Pooling
- Current: ~200 connections/minute
- Target: Reuse connections with PgBouncer
- Reduce connection overhead by 80%

### 6. Kubernetes Resource Optimization

#### Strategy 6A: Vertical Pod Autoscaling
- VPA recommends optimal resource requests/limits
- Run VPA in recommendation mode for 2 weeks
- Apply recommendations during maintenance window

#### Strategy 6B: Cluster Autoscaler
- Scale node groups based on pod resource requests
- Use diverse instance types for spot flexibility
- Configuration:
  - Scale-down threshold: 50% utilization for 10 min
  - Scale-up threshold: 70% utilization

---

## Implementation Timeline

### Phase 1: Quick Wins (Week 1)
- [ ] Reduce Redis to r6g.large
- [ ] Migrate EBS volumes to gp3
- [ ] Implement response compression
- [ ] Set log lifecycle policies

### Phase 2: Scheduling (Week 2-3)
- [ ] Migrate Celery workers to spot instances
- [ ] Right-size API pod resources
- [ ] Deploy VPA in recommendation mode

### Phase 3: Architecture (Month 2)
- [ ] Evaluate Aurora Serverless v2 migration
- [ ] Implement local cache layer
- [ ] Deploy read replicas for reporting

---

## Monitoring & Governance

### Cost Alerts
- Budget threshold: $1,200/month (hard limit)
- Alert at 80% ($960) and 90% ($1,080)
- Anomaly detection: >20% weekly increase

### Cost Visibility
- Kubernetes: Kubecost or OpenCost
- AWS: Cost Explorer with resource tags
- Tagging: All resources tagged with `CostCenter: PayShield`

### Optimization Reviews
- Weekly: Check unused resources (idle LBs, unattached volumes)
- Monthly: Right-sizing review vs actual usage
- Quarterly: Reserved instance / savings plan assessment

---

## Kubernetes Resource Recommendations

| Component | Current Request | Recommended Request | Savings |
|-----------|----------------|-------------------|---------|
| payshield-api | 500m CPU / 512Mi | 250m CPU / 384Mi | ~$60/mo |
| celery-worker | 1 CPU / 1Gi | 500m CPU / 768Mi | ~$40/mo |
| redis | 200m CPU / 256Mi | 100m CPU / 128Mi | ~$10/mo |
| postgres | 500m CPU / 512Mi | 250m CPU / 384Mi | ~$20/mo |

### Environment-Specific Configs

**Development:**
- 1 replica per service
- Minimum resource requests
- No HPA (manual scaling only)
- Estimated cost: ~$80/month

**Staging:**
- 2 replicas per service
- 50% of production resources
- HPA with lower limits
- Estimated cost: ~$200/month

**Production:**
- 3+ replicas with HPA
- Spot instances for workers
- Reserved instances for stateful services
- Estimated cost: ~$874/month (optimized)
