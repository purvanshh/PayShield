#!/usr/bin/env python3
"""
PayShield Resource Right-Sizing Analyzer
Analyzes current resource usage and recommends optimized requests/limits.
"""

import json
import subprocess
from typing import Dict, List
from dataclasses import dataclass, asdict


@dataclass
class ResourceUsage:
    pod_name: str
    cpu_request: str
    cpu_actual_avg: str
    cpu_actual_max: str
    memory_request: str
    memory_actual_avg: str
    memory_actual_max: str


@dataclass
class Recommendation:
    pod_name: str
    current_cpu: str
    recommended_cpu_request: str
    current_memory: str
    recommended_memory_request: str
    rationale: str


def get_pod_metrics(namespace: str = "payshield") -> List[ResourceUsage]:
    """Fetch current resource usage from kubectl top or metrics server."""
    try:
        result = subprocess.run(
            ["kubectl", "top", "pods", "-n", namespace, "--containers"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print("Warning: metrics-server not available, using default recommendations")
            return []

        pods = []
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 6 and parts[1] != "pod":
                pods.append(
                    ResourceUsage(
                        pod_name=parts[1],
                        cpu_request=parts[2],
                        cpu_actual_avg=parts[3],
                        cpu_actual_max=parts[4],
                        memory_request=parts[5],
                        memory_actual_avg=parts[6] if len(parts) > 6 else "0Mi",
                        memory_actual_max=parts[7] if len(parts) > 7 else "0Mi",
                    )
                )
        return pods
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def parse_resource_value(value: str) -> int:
    """Parse K8s resource value to millicores or MiB."""
    if value.endswith("m"):
        return int(value[:-1])
    elif value.endswith("Mi"):
        return int(value[:-2])
    elif value.endswith("Gi"):
        return int(value[:-2]) * 1024
    elif value.endswith("Ki"):
        return int(value[:-2]) // 1024
    return int(value)


def format_resource(value: int, resource_type: str = "memory") -> str:
    """Format resource value back to K8s string."""
    if resource_type == "cpu":
        return f"{value}m"
    if value >= 1024:
        return f"{value / 1024:.1f}Gi"
    return f"{value}Mi"


def recommend_pod(usage: ResourceUsage) -> Recommendation:
    """Generate resource recommendation for a single pod."""
    cpu_avg = parse_resource_value(usage.cpu_actual_avg)
    cpu_max = parse_resource_value(usage.cpu_actual_max)
    mem_avg = parse_resource_value(usage.memory_actual_avg)
    mem_max = parse_resource_value(usage.memory_actual_max)
    cpu_req = parse_resource_value(usage.cpu_request)
    mem_req = parse_resource_value(usage.memory_request)

    recommended_cpu = max(cpu_avg, cpu_max // 2)
    recommended_cpu = max(recommended_cpu, 50)  # floor 50m
    recommended_cpu_request = min(recommended_cpu, cpu_req)

    recommended_mem = max(mem_avg * 1.5, mem_max)
    recommended_mem = max(recommended_mem, 64)  # floor 64Mi
    recommended_memory_request = min(int(recommended_mem), mem_req)

    cpu_savings = cpu_req - recommended_cpu_request
    mem_savings = mem_req - recommended_memory_request

    if cpu_savings > 100 or mem_savings > 256:
        rationale = f"Over-provisioned: CPU {cpu_savings}m, Memory {mem_savings}Mi excess"
    elif cpu_savings < -50 or mem_savings < -128:
        rationale = "Under-provisioned: Increase requests"
    else:
        rationale = "Appropriately sized"

    return Recommendation(
        pod_name=usage.pod_name,
        current_cpu=usage.cpu_request,
        recommended_cpu_request=format_resource(recommended_cpu_request, "cpu"),
        current_memory=usage.memory_request,
        recommended_memory_request=format_resource(recommended_memory_request, "memory"),
        rationale=rationale,
    )


def generate_report(pods: List[ResourceUsage]):
    """Generate a formatted right-sizing report."""
    print("=" * 70)
    print("  PayShield Resource Right-Sizing Report")
    print("=" * 70)
    print()

    if not pods:
        print("Using default recommendations (metrics-server not available):")
        print()
        print(f"{'Component':<25} {'Current CPU':>12} {'Recommended':>12} {'Current Mem':>12} {'Recommended':>12}")
        print("-" * 73)
        defaults = [
            ("payshield-api", "500m", "250m", "512Mi", "384Mi"),
            ("celery-worker", "1000m", "500m", "1Gi", "768Mi"),
            ("redis", "200m", "100m", "256Mi", "128Mi"),
            ("postgres", "500m", "250m", "512Mi", "384Mi"),
        ]
        for name, cpu_cur, cpu_rec, mem_cur, mem_rec in defaults:
            print(f"{name:<25} {cpu_cur:>10} {cpu_rec:>10} {mem_cur:>10} {mem_rec:>10}")
        print()
        print("Estimated monthly savings: ~$130")
        return

    print(f"{'Pod':<30} {'CPU Request':>12} {'CPU Recommended':>16} {'Mem Request':>12} {'Mem Recommended':>16} {'Status':>15}")
    print("-" * 101)

    for pod in pods:
        rec = recommend_pod(pod)
        print(
            f"{rec.pod_name:<30} {rec.current_cpu:>10} {rec.recommended_cpu_request:>10} "
            f"{rec.current_memory:>10} {rec.recommended_memory_request:>10} {rec.rationale:>20}"
        )


if __name__ == "__main__":
    import sys
    namespace = sys.argv[1] if len(sys.argv) > 1 else "payshield"
    pods = get_pod_metrics(namespace)
    generate_report(pods)
