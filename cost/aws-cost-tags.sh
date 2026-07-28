#!/usr/bin/env bash
set -euo pipefail

# Apply cost allocation tags to all PayShield AWS resources
ENVIRONMENT="${1:-production}"
REGION="${2:-us-east-1}"

COMMON_TAGS=(
    "Key=Project,Value=PayShield"
    "Key=Environment,Value=${ENVIRONMENT}"
    "Key=CostCenter,Value=Engineering-FraudDetection"
    "Key=ManagedBy,Value=Terraform"
    "Key=Contact,Value=devops@payshield.io"
)

echo "=== Applying cost tags to AWS resources ==="
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"
echo ""

TAG_SPEC=$(IFS=,; echo "${COMMON_TAGS[*]}")

# Tag EC2 instances
echo "--- Tagging EC2 instances ---"
aws ec2 describe-instances --region "${REGION}" \
    --filters "Name=tag:Project,Values=PayShield" \
    --query "Reservations[].Instances[].InstanceId" \
    --output text | tr '\t' '\n' | while read -r instance_id; do
    if [ -n "${instance_id}" ]; then
        aws ec2 create-tags --region "${REGION}" \
            --resources "${instance_id}" \
            --tags ${COMMON_TAGS[@]}
        echo "Tagged EC2: ${instance_id}"
    fi
done

# Tag RDS instances
echo "--- Tagging RDS instances ---"
aws rds describe-db-instances --region "${REGION}" \
    --query "DBInstances[?contains(DBInstanceIdentifier, 'payshield')].DBInstanceIdentifier" \
    --output text | tr '\t' '\n' | while read -r db_id; do
    if [ -n "${db_id}" ]; then
        aws rds add-tags-to-resource --region "${REGION}" \
            --resource-name "arn:aws:rds:${REGION}:$(aws sts get-caller-identity --query Account --output text):db:${db_id}" \
            --tags ${COMMON_TAGS[@]}
        echo "Tagged RDS: ${db_id}"
    fi
done

# Tag ElastiCache clusters
echo "--- Tagging ElastiCache clusters ---"
aws elasticache describe-cache-clusters --region "${REGION}" \
    --query "CacheClusters[?contains(CacheClusterId, 'payshield')].CacheClusterId" \
    --output text | tr '\t' '\n' | while read -r cache_id; do
    if [ -n "${cache_id}" ]; then
        CACHE_ARN="arn:aws:elasticache:${REGION}:$(aws sts get-caller-identity --query Account --output text):cluster:${cache_id}"
        aws elasticache add-tags-to-resource --region "${REGION}" \
            --resource-name "${CACHE_ARN}" \
            --tags ${COMMON_TAGS[@]}
        echo "Tagged ElastiCache: ${cache_id}"
    fi
done

# Tag S3 buckets
echo "--- Tagging S3 buckets ---"
aws s3api list-buckets --query "Buckets[?contains(Name, 'payshield')].Name" \
    --output text | tr '\t' '\n' | while read -r bucket; do
    if [ -n "${bucket}" ]; then
        aws s3api put-bucket-tagging --bucket "${bucket}" \
            --tagging "TagSet=[$(IFS=,; echo "${COMMON_TAGS[*]}")]"
        echo "Tagged S3: ${bucket}"
    fi
done

# Tag Load Balancers
echo "--- Tagging Load Balancers ---"
aws elbv2 describe-load-balancers --region "${REGION}" \
    --query "LoadBalancers[?contains(LoadBalancerName, 'payshield')].LoadBalancerArn" \
    --output text | tr '\t' '\n' | while read -r lb_arn; do
    if [ -n "${lb_arn}" ]; then
        aws elbv2 add-tags --region "${REGION}" \
            --resource-arns "${lb_arn}" \
            --tags ${COMMON_TAGS[@]}
        echo "Tagged LB: ${lb_arn}"
    fi
done

echo ""
echo "=== Cost tagging complete ==="
echo "Run: aws costexplorer get-cost-and-usage to verify"
