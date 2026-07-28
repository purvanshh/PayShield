#!/usr/bin/env python3
"""
PayShield Cost Savings Calculator
Estimates monthly savings from optimization strategies.
"""

# AWS Pricing (us-east-1, as of 2026)
PRICING = {
    "api_pod": {
        "on_demand": {"m5_large": 0.096},
        "spot": {"m5_large": 0.0288},
        "reserved_1yr": {"m5_large": 0.061},
    },
    "celery_pod": {
        "on_demand": {"c5_xlarge": 0.170},
        "spot": {"c5_xlarge": 0.051},
        "reserved_1yr": {"c5_xlarge": 0.108},
    },
    "redis": {
        "on_demand": {"r5_large": 0.175, "r6g_large": 0.128},
        "reserved_1yr": {"r5_large": 0.112, "r6g_large": 0.082},
    },
    "postgres": {
        "on_demand": {"r5_xlarge": 0.480},
        "serverless": {"per_acu_hour": 0.120},
        "reserved_1yr": {"r5_xlarge": 0.307},
    },
    "storage": {"gp2_per_gb": 0.10, "gp3_per_gb": 0.08},
}


def hours_per_month(days=30):
    return days * 24


def gibi_to_gib(gib):
    return gib


def calculate_api_savings(replicas=3, hours=None):
    hours = hours or hours_per_month()
    od = replicas * hours * PRICING["api_pod"]["on_demand"]["m5_large"]
    spot = replicas * hours * PRICING["api_pod"]["spot"]["m5_large"]
    reserved = replicas * hours * PRICING["api_pod"]["reserved_1yr"]["m5_large"]
    return {"on_demand": od, "spot": spot, "reserved": reserved, "savings_spot": od - spot}


def calculate_celery_savings(replicas=2, hours=None):
    hours = hours or hours_per_month()
    od = replicas * hours * PRICING["celery_pod"]["on_demand"]["c5_xlarge"]
    spot = replicas * hours * PRICING["celery_pod"]["spot"]["c5_xlarge"]
    return {"on_demand": od, "spot": spot, "savings_spot": od - spot}


def calculate_redis_savings():
    hours = hours_per_month()
    od = hours * PRICING["redis"]["on_demand"]["r5_large"]
    reserved = hours * PRICING["redis"]["reserved_1yr"]["r6g_large"]
    return {"current": od, "optimized": reserved, "savings": od - reserved}


def calculate_postgres_savings():
    hours = hours_per_month()
    od = hours * PRICING["postgres"]["on_demand"]["r5_xlarge"]
    reserved = hours * PRICING["postgres"]["reserved_1yr"]["r5_xlarge"]
    serverless = hours * PRICING["postgres"]["serverless"]["per_acu_hour"] * 4  # avg 4 ACU
    return {"on_demand": od, "reserved": reserved, "serverless": serverless, "savings_reserved": od - reserved}


def calculate_storage_savings():
    gp2 = 100 * PRICING["storage"]["gp2_per_gb"]
    gp3 = 100 * PRICING["storage"]["gp3_per_gb"]
    return {"gp2": gp2, "gp3": gp3, "savings": gp2 - gp3}


def print_report():
    print("=" * 60)
    print("  PayShield Cost Savings Report")
    print("=" * 60)
    print()

    api = calculate_api_savings()
    celery = calculate_celery_savings()
    redis = calculate_redis_savings()
    postgres = calculate_postgres_savings()
    storage = calculate_storage_savings()

    total_current = api["on_demand"] + celery["on_demand"] + redis["current"] + postgres["on_demand"] + storage["gp2"]
    total_optimized = api["spot"] + celery["spot"] + redis["optimized"] + postgres["reserved"] + storage["gp3"]

    print(f"{'Component':<25} {'Current':>10} {'Optimized':>10} {'Savings':>10}")
    print("-" * 55)
    print(f"{'API Pods':<25} {api['on_demand']:>8.2f} {api['spot']:>8.2f} {api['savings_spot']:>8.2f}")
    print(f"{'Celery Workers':<25} {celery['on_demand']:>8.2f} {celery['spot']:>8.2f} {celery['savings_spot']:>8.2f}")
    print(f"{'Redis':<25} {redis['current']:>8.2f} {redis['optimized']:>8.2f} {redis['savings']:>8.2f}")
    print(f"{'PostgreSQL':<25} {postgres['on_demand']:>8.2f} {postgres['reserved']:>8.2f} {postgres['savings_reserved']:>8.2f}")
    print(f"{'Storage':<25} {storage['gp2']:>8.2f} {storage['gp3']:>8.2f} {storage['savings']:>8.2f}")
    print("-" * 55)
    print(f"{'TOTAL':<25} {total_current:>8.2f} {total_optimized:>8.2f} {total_current - total_optimized:>8.2f}")
    print()
    print(f"Monthly Savings: ${total_current - total_optimized:.2f}")
    print(f"Annual Savings: ${(total_current - total_optimized) * 12:.2f}")
    print(f"Reduction: {(1 - total_optimized / total_current) * 100:.1f}%")


if __name__ == "__main__":
    print_report()
