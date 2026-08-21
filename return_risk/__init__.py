"""Return-risk scorer package (Track 02 - AI Risk Manager).

Package layout:
- feature_engine.py    -- extract user/merchant/txn features (Phase 13)
- rules_engine.py      -- fire R-RULE-* definitions (Phase 14)
- scorer.py            -- weighted composite score (Phase 15)
- recommendations.py   -- action -> merchant-facing recommendations
"""

from return_risk.recommendations import recommendations_for_action

__all__ = ["recommendations_for_action"]

__version__ = "1.0.0"
