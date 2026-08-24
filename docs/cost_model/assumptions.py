"""Cost-model assumptions for the false-positive return-risk analysis.

Every number here is a configurable, documented assumption drawn from
Indian e-commerce unit economics (2026) so the calculator can be re-run
with a merchant's own numbers. Sources are listed inline; the full table
lives in ``docs/COST_MODEL.md``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CostAssumptions:
    """Single set of merchant unit economics.

    All monetary values are in Indian rupees (₹).
    """

    aov: float = 2500.0  # Average Order Value (Myntra/Flipkart/Amazon IN median)
    return_rate: float = 0.18  # unscored return rate (post-festive baseline)
    return_logistics: float = 120.0  # reverse pickup + QC
    restocking: float = 80.0  # repackaging + warehouse handling
    service_cost: float = 45.0  # call centre + chatbot escalation per return
    gateway_fee_pct: float = 0.02  # non-refundable Razorpay fee, % of AOV
    cac: float = 180.0  # blended digital-marketing acquisition cost
    churn_after_false_block: float = 0.15  # probability the blocked customer churns
    ltv: float = 3000.0  # expected lifetime value of a good customer
    diversion_effectiveness: float = 0.70  # share of diverted orders that don't return
    review_cost: float = 200.0  # operator time to manually review one flag (not the order value)

    @property
    def gateway_fee(self) -> float:
        """Non-refundable payment-processing fee in ₹ (AOV × rate)."""
        return self.aov * self.gateway_fee_pct

    @property
    def false_allow_cost(self) -> float:
        """Cost when a high-risk return slips through and actually returns."""
        return (
            self.aov
            + self.return_logistics
            + self.restocking
            + self.service_cost
            + self.gateway_fee
        )

    @property
    def false_block_cost(self) -> float:
        """Cost when a good customer's order is wrongly flagged.

        Direct = money, gateway fee and acquisition cost already spent on an
        order that never ships. Indirect = expected forgone lifetime value from
        the probabilty the customer churns after a bad experience.
        """
        direct = self.aov + self.gateway_fee + self.cac
        indirect = self.churn_after_false_block * self.ltv
        return direct + indirect
