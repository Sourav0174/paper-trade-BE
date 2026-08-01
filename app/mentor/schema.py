"""
Schema definitions for the AI Mentor Analytics & Rule Engine modules.

This module defines pure data contracts for FIFO reconstruction objects,
holding states, computed analytics metrics, and rule insights.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TradeInput(BaseModel):
    """Normalized input trade representation for FIFO processing."""

    id: int | str = Field(description="Unique trade identifier")
    symbol: str = Field(description="Stock ticker symbol (e.g. RELIANCE)")
    quantity: int = Field(gt=0, description="Quantity of shares traded")
    price: float = Field(gt=0.0, description="Execution price per share")
    trade_type: str = Field(description="Trade direction: BUY or SELL")
    created_at: datetime = Field(description="Execution timestamp")


class TradeLot(BaseModel):
    """Represents an active or partially filled BUY lot in the FIFO queue."""

    trade_id: int | str = Field(description="Originating buy trade ID")
    symbol: str = Field(description="Stock ticker symbol")
    price: float = Field(description="Purchase price per share")
    quantity: int = Field(description="Original lot quantity")
    remaining_quantity: int = Field(description="Unmatched remaining quantity")
    timestamp: datetime = Field(description="Purchase timestamp")


class ClosedTradeChunk(BaseModel):
    """Represents a matched sub-lot pair between a BUY trade and a SELL trade."""

    buy_trade_id: int | str = Field(description="Matched buy trade ID")
    sell_trade_id: int | str = Field(description="Matched sell trade ID")
    symbol: str = Field(description="Stock ticker symbol")
    buy_price: float = Field(description="Buy price per share")
    sell_price: float = Field(description="Sell price per share")
    quantity: int = Field(description="Matched quantity of shares")
    buy_timestamp: datetime = Field(description="Buy timestamp")
    sell_timestamp: datetime = Field(description="Sell timestamp")
    pnl: float = Field(description="Realized profit/loss amount")
    pnl_percent: float = Field(description="Realized profit/loss percentage")
    duration_minutes: float = Field(description="Holding duration in minutes")


class ClosedPosition(BaseModel):
    """Represents a consolidated round-trip position campaign (0 -> N -> 0 shares)."""

    position_id: str = Field(description="Unique generated position ID")
    symbol: str = Field(description="Stock ticker symbol")
    total_quantity: int = Field(description="Total quantity accumulated and closed")
    weighted_avg_buy_price: float = Field(description="Weighted average buy price")
    weighted_avg_sell_price: float = Field(description="Weighted average sell price")
    realized_pnl: float = Field(description="Total realized P&L for position")
    realized_pnl_percent: float = Field(description="Total realized P&L percentage")
    open_timestamp: datetime = Field(description="Position opening timestamp (first buy)")
    close_timestamp: datetime = Field(description="Position closing timestamp (final sell)")
    holding_duration_minutes: float = Field(description="Total campaign duration in minutes")
    is_win: bool = Field(description="True if realized_pnl > 0")
    is_loss: bool = Field(description="True if realized_pnl < 0")
    is_breakeven: bool = Field(description="True if realized_pnl == 0")
    chunks: List[ClosedTradeChunk] = Field(default_factory=list, description="Sub-lot chunks making up this position")


class OpenPositionState(BaseModel):
    """Represents currently open holdings reconstructed from unmatched BUY lots."""

    symbol: str = Field(description="Stock ticker symbol")
    total_quantity: int = Field(description="Total open quantity")
    weighted_avg_buy_price: float = Field(description="Weighted average buy price")
    total_invested_amount: float = Field(description="Total capital invested in open lots")
    earliest_buy_timestamp: datetime = Field(description="Timestamp of earliest open buy lot")
    lots: List[TradeLot] = Field(default_factory=list, description="Active remaining buy lots")


class HoldingItem(BaseModel):
    """Represents an active user holding for portfolio concentration (HHI) calculation."""

    symbol: str = Field(description="Stock ticker symbol")
    quantity: int = Field(description="Quantity owned")
    avg_price: float = Field(default=0.0, description="Average cost basis per share")
    current_price: float = Field(description="Current market price per share")
    current_value: float = Field(description="Total current market value (quantity * price)")


class FifoReconstructionResult(BaseModel):
    """Complete output of the FIFO position reconstruction engine."""

    closed_positions: List[ClosedPosition] = Field(default_factory=list)
    closed_chunks: List[ClosedTradeChunk] = Field(default_factory=list)
    open_positions: Dict[str, OpenPositionState] = Field(default_factory=dict)
    unmatched_sells: List[dict] = Field(default_factory=list)


class AnalyticsMetrics(BaseModel):
    """Deterministic trading performance and behavioral metrics."""

    total_trades_count: int = Field(description="Total raw trades executed")
    closed_positions_count: int = Field(description="Total closed position campaigns")
    winning_positions_count: int = Field(description="Number of profitable closed positions")
    losing_positions_count: int = Field(description="Number of unprofitable closed positions")
    breakeven_positions_count: int = Field(description="Number of breakeven closed positions")

    win_rate_pct: float = Field(description="Percentage of winning closed positions (0-100)")
    total_realized_pnl: float = Field(description="Total cumulative realized P&L across all closed positions")
    total_gross_profit: float = Field(description="Sum of profits from winning positions")
    total_gross_loss: float = Field(description="Sum of losses from losing positions (positive value)")

    average_profit: float = Field(description="Average profit per winning position")
    average_loss: float = Field(description="Average loss per losing position (positive value)")
    profit_factor: float = Field(description="Gross profit / Gross loss ratio")
    risk_reward_ratio: float = Field(description="Average profit / Average loss ratio")

    max_drawdown_pct: float = Field(description="Maximum peak-to-trough equity drop percentage")
    max_drawdown_amount: float = Field(description="Maximum peak-to-trough equity drop currency amount")

    avg_holding_duration_minutes: float = Field(description="Average holding duration of all closed positions")
    avg_winning_duration_minutes: float = Field(description="Average holding duration of winning positions")
    avg_losing_duration_minutes: float = Field(description="Average holding duration of losing positions")
    holding_duration_ratio: float = Field(description="Losing duration / Winning duration ratio")

    portfolio_concentration_hhi: float = Field(description="Herfindahl-Hirschman Index for portfolio holdings")
    max_position_sizing_pct: float = Field(description="Largest single position size relative to portfolio value")
    avg_position_sizing_pct: float = Field(description="Average position size relative to portfolio value")
    total_unrealized_pnl: Optional[float] = Field(default=None, description="Current unrealized P&L if market prices supplied")


class Severity(str, Enum):
    """Severity classification for rule insights."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Confidence(str, Enum):
    """Confidence level of rule evaluation."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class InsightCategory(str, Enum):
    """Category classification of detected behavior."""

    MISTAKE = "MISTAKE"
    STRENGTH = "STRENGTH"
    RISK_WARNING = "RISK_WARNING"
    HABIT = "HABIT"


class Insight(BaseModel):
    """Structured insight output generated by a triggered rule."""

    rule_id: str = Field(description="Unique rule identifier")
    category: InsightCategory = Field(description="Category of detected behavior")
    title: str = Field(description="Short human-readable title of insight")
    description: str = Field(description="Detailed explanation of the behavioral pattern")
    severity: Severity = Field(description="Severity impact level")
    confidence: Confidence = Field(description="Confidence level of rule detection")
    metrics_context: dict = Field(default_factory=dict, description="Quantitative context snapshot")
    coaching_message: str = Field(description="Actionable mentoring feedback")
    action_item: str = Field(description="Concrete recommended habit or step")


class RuleResult(BaseModel):
    """Result returned by an individual rule evaluation."""

    is_triggered: bool = Field(description="True if rule criteria met")
    insight: Optional[Insight] = Field(default=None, description="Generated Insight if triggered")


class TradingGrade(str, Enum):
    """Overall trading performance grade classification."""

    MASTER = "MASTER"
    DISCIPLINED = "DISCIPLINED"
    AVERAGE = "AVERAGE"
    NEEDS_WORK = "NEEDS_WORK"
    HIGH_RISK = "HIGH_RISK"


class MentorSummary(BaseModel):
    """Consolidated summary produced by the Insight Prioritizer."""

    trading_health_score: float = Field(description="Overall Trading Health Score from 0.0 to 100.0")
    grade: TradingGrade = Field(description="Performance grade based on health score")
    portfolio_summary: dict = Field(description="Quantitative snapshot of performance and health sub-scores")
    top_strengths: List[Insight] = Field(default_factory=list, description="Top positive insights (max 3)")
    top_mistakes: List[Insight] = Field(default_factory=list, description="Top behavioral mistakes (max 3)")
    top_risks: List[Insight] = Field(default_factory=list, description="Top risk warnings (max 3)")
    action_items: List[str] = Field(default_factory=list, description="Prioritized concrete action items (max 3)")
    improvement_focus: str = Field(description="Single primary focus area for coaching")
    all_insights: List[Insight] = Field(default_factory=list, description="All evaluated insights after deduplication")

