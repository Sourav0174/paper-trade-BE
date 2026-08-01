"""
AI Mentor Domain Module.

Phase 1: Analytics Foundation.
Phase 2: Deterministic Rule Engine.
Phase 2.5: Insight Prioritizer & Mentor Summary.
Contains FIFO trade reconstruction, deterministic analytics, modular rules, insight prioritization, and schemas.
"""

from app.mentor.schema import (
    AnalyticsMetrics,
    ClosedPosition,
    ClosedTradeChunk,
    Confidence,
    FifoReconstructionResult,
    HoldingItem,
    Insight,
    InsightCategory,
    MentorSummary,
    OpenPositionState,
    RuleResult,
    Severity,
    TradeInput,
    TradeLot,
    TradingGrade,
)
from app.mentor.fifo import FIFOReconstructor
from app.mentor.analytics import AnalyticsEngine
from app.mentor.rule_engine import (
    BaseRule,
    ConcentrationRiskRule,
    DrawdownRule,
    FOMOBuyingRule,
    HoldingDurationAsymmetryRule,
    OvertradingRule,
    PositionSizingRule,
    RevengeTradingRule,
    RiskRewardRatioRule,
    RuleEngine,
    StopLossDisciplineRule,
)
from app.mentor.prioritizer import InsightPrioritizer

__all__ = [
    "TradeInput",
    "TradeLot",
    "ClosedTradeChunk",
    "ClosedPosition",
    "OpenPositionState",
    "HoldingItem",
    "FifoReconstructionResult",
    "AnalyticsMetrics",
    "Severity",
    "Confidence",
    "InsightCategory",
    "Insight",
    "RuleResult",
    "TradingGrade",
    "MentorSummary",
    "FIFOReconstructor",
    "AnalyticsEngine",
    "BaseRule",
    "RevengeTradingRule",
    "FOMOBuyingRule",
    "PositionSizingRule",
    "HoldingDurationAsymmetryRule",
    "RiskRewardRatioRule",
    "ConcentrationRiskRule",
    "OvertradingRule",
    "DrawdownRule",
    "StopLossDisciplineRule",
    "RuleEngine",
    "InsightPrioritizer",
]
