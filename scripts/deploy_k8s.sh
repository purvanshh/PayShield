#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="payshield"
ENV="${1:-dev}"
CLUSTER_NAME="${2:-payshield-cluster}"

echo "=== Deploying PayShield to environment: ${ENV} ==="

if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl not found"
    exit 1
fi

if ! command -v kustomize &> /dev/null; then
    echo "Error: kustomize not found"
    exit 1
fi

echo "--- Creating namespace ---"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "--- Applying sealed secrets ---"
if [ -f "k8s/overlays/${ENV}/sealed-secrets.yaml" ]; then
    kubectl apply -f "k8s/overlays/${ENV}/sealed-secrets.yaml"
else
    echo "Warning: No sealed secrets found for ${ENV}, using base"
    kubectl apply -f k8s/base/payshield-sealed-secret.yaml
fi

echo "--- Building and applying Kustomize overlay ---"
kustomize build "k8s/overlays/${ENV}" | kubectl apply -f -

echo "--- Waiting for deployments ---"
kubectl -n "${NAMESPACE}" wait --for=condition=Available --timeout=300s \
    deployment/payshield-api \
    deployment/redis \
    deployment/payshield-celery-worker

echo "--- Waiting for statefulset ---"
kubectl -n "${NAMESPACE}" wait --for=condition=Ready --timeout=300s pod -l app.kubernetes.io/component=postgres

echo "=== Deployment complete ==="
echo ""
echo "Useful commands:"
echo "  kubectl -n ${NAMESPACE} get pods"
echo "  kubectl -n ${NAMESPACE} get svc"
echo "  kubectl -n ${NAMESPACE} logs -l app.kubernetes.io/component=api"
