import math

import numpy as np
from scipy.stats import chi2


def benford_expected_distribution() -> np.ndarray:
    return np.array([math.log10(1 + 1 / d) for d in range(1, 10)])


def first_digit_frequencies(amounts: list[float]) -> np.ndarray:
    pass


def benford_chi2(amounts: list[float]) -> float:
    pass
