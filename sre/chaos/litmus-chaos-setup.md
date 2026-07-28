# LitmusChaos Setup

## Installation

```bash
# Install LitmusChaos 3.x
kubectl apply -f https://litmuschaos.github.io/litmus/litmus-operator-v3.0.0.yaml

# Verify installation
kubectl get pods -n litmus

# Install chaos experiments
kubectl apply -f https://hub.litmuschaos.io/api/chaos/3.0.0?file=charts/generic/pod-delete/experiment.yaml
kubectl apply -f https://hub.litmuschaos.io/api/chaos/3.0.0?file=charts/generic/pod-network-partition/experiment.yaml
kubectl apply -f https://hub.litmuschaos.io/api/chaos/3.0.0?file=charts/generic/pod-network-latency/experiment.yaml
kubectl apply -f https://hub.litmuschaos.io/api/chaos/3.0.0?file=charts/generic/node-drain/experiment.yaml
kubectl apply -f https://hub.litmuschaos.io/api/chaos/3.0.0?file=charts/generic/pod-cpu-hog/experiment.yaml
```

## Service Account

```bash
kubectl create serviceaccount litmus-admin -n payshield
kubectl create clusterrolebinding litmus-admin --serviceaccount=payshield:litmus-admin --clusterrole=cluster-admin
```

## Running Experiments

```bash
# Dry run
kubectl create -f sre/chaos/experiments/api-pod-failure.yaml --dry-run=client

# Execute
kubectl create -f sre/chaos/experiments/api-pod-failure.yaml

# Monitor
kubectl describe chaosengine api-pod-failure -n payshield
kubectl get chaosresult -n payshield -w

# Cleanup
kubectl delete chaosengine api-pod-failure -n payshield
```

## Experiment Schedule

| Frequency | Experiment | Environment |
|-----------|------------|-------------|
| Daily | API pod failure | Staging |
| Weekly | Redis network partition | Staging |
| Monthly | PostgreSQL high latency | Staging |
| Quarterly | Full game day (all experiments) | Staging |
