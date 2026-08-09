"""
AI Mentor Domain Module.

Phase 1: Analytics Foundation.
Phase 2: Deterministic Rule Engine.
Phase 2.5: Insight Prioritizer & Mentor Summary.
Phase 3A: AI Generation Layer.
Phase 3B: Mentor Service Orchestration Layer.
Contains FIFO trade reconstruction, deterministic analytics, modular rules, prioritizer, prompt builder, guardrails, generators, and service orchestrator.
"""

from app.mentor.schema import (
    AnalyticsMetrics,
    ClosedPosition,
    ClosedTradeChunk,
    Confidence,
    DailyMentorReview,
    FifoReconstructionResult,
    HoldingItem,
    Insight,
    InsightCategory,
    MentorResponse,
    MentorSummary,
    OpenPositionState,
    PromptContext,
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
from app.mentor.service import MentorService

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
    "PromptContext",
    "MentorResponse",
    "DailyMentorReview",
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
    "MentorService",
]
