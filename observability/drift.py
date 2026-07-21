import numpy as np
from scipy.stats import chisquare


def population_stability_index(expected: np.ndarray, actual: np.ndarray) -> float:
    pass


class DriftDetector:
    def __init__(self, threshold: float = 0.25):
        self.threshold = threshold

    def check_feature(self, name: str, expected: np.ndarray, actual: np.ndarray) -> bool:
        pass
