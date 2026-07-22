import math

import numpy as np
from scipy.stats import chi2


def benford_expected_distribution() -> np.ndarray:
    return np.array([math.log10(1 + 1 / d) for d in range(1, 10)])


def first_digit_frequencies(amounts: list[float]) -> np.ndarray:
    if not amounts:
        return np.zeros(9)
    digits = []
    for amt in amounts:
        s = f"{abs(amt):.2f}"
        for ch in s:
            if ch.isdigit() and ch != "0":
                digits.append(int(ch))
                break
    counts = np.zeros(9)
    for d in digits:
        if 1 <= d <= 9:
            counts[d - 1] += 1
    total = counts.sum()
    if total == 0:
        return np.zeros(9)
    return counts / total


def benford_chi2(amounts: list[float]) -> float:
    if len(amounts) < 20:
        return 0.0
    observed = first_digit_frequencies(amounts)
    expected = benford_expected_distribution()
    n = len(amounts)
    chi2_stat = np.sum((observed * n - expected * n) ** 2 / (expected * n + 1e-10))
    return float(chi2_stat)
