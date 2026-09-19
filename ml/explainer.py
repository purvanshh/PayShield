"""Compatibility shim: explainer module moved to engine.explainer."""

from engine.explainer import (
    ExplanationResult,
    ExplanationFormatter,
    DualExplanationMerger,
    FraudPattern,
    GNNExplainerWrapper,
    PyGGNNExplainerWrapper,
    SHAPBridge,
    SHAPFeatureBridge,
    SHAPResult,
    UnifiedEvidence,
)

__all__ = [
    "ExplanationResult",
    "ExplanationFormatter",
    "DualExplanationMerger",
    "FraudPattern",
    "GNNExplainerWrapper",
    "PyGGNNExplainerWrapper",
    "SHAPBridge",
    "SHAPFeatureBridge",
    "SHAPResult",
    "UnifiedEvidence",
]