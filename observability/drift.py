import numpy as np


def population_stability_index(expected: np.ndarray, actual: np.ndarray,
                               n_bins: int | None = None, alpha: float = 0.5) -> float:
    """Population Stability Index between two distributions.

    Robust against the common false-spike causes:
    - shared bin edges computed from the COMBINED distribution (no binning mismatch)
    - bin count scaled to sample size (never more bins than the data supports)
    - Laplace smoothing (alpha) so zero-mass bins cannot produce infinite PSI
    - quantile edges handle skewed monetary aggregates (no need for log-binning)
    """
    if len(expected) == 0 or len(actual) == 0:
        return 0.0

    n = min(len(expected), len(actual))
    if n_bins is None:
        n_bins = min(10, max(3, n // 5))

    combined = np.concatenate([expected, actual])
    lo, hi = float(np.min(combined)), float(np.max(combined))
    if hi <= lo:
        return 0.0

    edges = np.quantile(combined, np.linspace(0.0, 1.0, n_bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:
        # identical (or near-identical) values -> no observable shift
        return 0.0

    expected_counts, _ = np.histogram(expected, bins=edges)
    actual_counts, _ = np.histogram(actual, bins=edges)

    expected_sm = expected_counts + alpha
    actual_sm = actual_counts + alpha
    expected_perc = expected_sm / expected_sm.sum()
    actual_perc = actual_sm / actual_sm.sum()

    psi = np.sum((actual_perc - expected_perc) * np.log(actual_perc / expected_perc))
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
