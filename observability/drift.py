import numpy as np


def population_stability_index(expected: np.ndarray, actual: np.ndarray, n_bins: int = 10) -> float:
    if len(expected) == 0 or len(actual) == 0:
        return 0.0
    combined = np.concatenate([expected, actual])
    bins = np.linspace(np.min(combined), np.max(combined), n_bins + 1)
    expected_perc, _ = np.histogram(expected, bins=bins, density=True)
    actual_perc, _ = np.histogram(actual, bins=bins, density=True)
    expected_perc = expected_perc / expected_perc.sum() if expected_perc.sum() > 0 else expected_perc
    actual_perc = actual_perc / actual_perc.sum() if actual_perc.sum() > 0 else actual_perc
    psi = np.sum((actual_perc - expected_perc) * np.log((actual_perc + 1e-10) / (expected_perc + 1e-10)))
    return float(psi)


class DriftDetector:
    def __init__(self, threshold: float = 0.25):
        self.threshold = threshold
        self.reference_distributions: dict[str, np.ndarray] = {}

    def register_reference(self, name: str, values: np.ndarray):
        self.reference_distributions[name] = values.copy()

    def check_feature(self, name: str, actual: np.ndarray) -> bool:
        expected = self.reference_distributions.get(name)
        if expected is None or len(expected) == 0 or len(actual) == 0:
            return False
        psi = population_stability_index(expected, actual)
        return psi > self.threshold

    def get_psi(self, name: str, actual: np.ndarray) -> float:
        expected = self.reference_distributions.get(name)
        if expected is None:
            return 0.0
        return population_stability_index(expected, actual)
