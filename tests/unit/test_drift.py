import numpy as np

from observability.drift import DriftDetector, population_stability_index


class TestPSI:
    def test_identical_distributions(self):
        a = np.random.randn(1000)
        psi = population_stability_index(a, a)
        assert psi < 0.01

    def test_different_distributions(self):
        a = np.random.randn(1000)
        b = np.random.randn(1000) * 3 + 5
        psi = population_stability_index(a, b)
        assert psi > 0.01

    def test_empty_input(self):
        assert population_stability_index([], []) == 0.0
        assert population_stability_index([1, 2, 3], []) == 0.0

    def test_single_value(self):
        psi = population_stability_index([1.0], [2.0])
        assert isinstance(psi, float)


class TestDriftDetector:
    def test_no_drift_within_threshold(self):
        d = DriftDetector(threshold=0.25)
        d.register_reference("f1", np.random.randn(1000))
        assert not d.check_feature("f1", np.random.randn(1000))

    def test_drift_detected(self):
        d = DriftDetector(threshold=0.1)
        d.register_reference("f1", np.random.randn(1000))
        assert d.check_feature("f1", np.random.randn(1000) * 10 + 50)

    def test_unknown_feature(self):
        d = DriftDetector()
        assert not d.check_feature("unknown", np.array([1, 2, 3]))

    def test_get_psi(self):
        d = DriftDetector()
        d.register_reference("f1", np.array([1.0, 2.0, 3.0]))
        psi = d.get_psi("f1", np.array([1.5, 2.5, 3.5]))
        assert psi >= 0
