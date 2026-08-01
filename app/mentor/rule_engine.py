

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import List, Optional

from app.mentor.schema import (
    AnalyticsMetrics,
    ClosedPosition,
    Confidence,
    HoldingItem,
    Insight,
    InsightCategory,
    RuleResult,
    Severity,
    TradeInput,
)


class BaseRule(ABC):
    """Abstract base class for all deterministic mentor rules."""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier string."""
        pass

    @abstractmethod
    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        """
        Evaluates the rule against analytics metrics and supporting trade context.

        Returns:
            RuleResult with is_triggered boolean and optional Insight object.
        """
        pass


class RevengeTradingRule(BaseRule):
    """Rule 1: Detects revenge trading behavior (entering new trades shortly after a loss)."""

    @property
    def rule_id(self) -> str:
        return "MISTAKE_REVENGE_TRADING"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        if not closed_positions or metrics.losing_positions_count == 0:
            return RuleResult(is_triggered=False)

        losing_positions = [p for p in closed_positions if p.is_loss]
        sorted_positions = sorted(closed_positions, key=lambda p: p.open_timestamp)

        revenge_count = 0
        revenge_details = []

        for loss_pos in losing_positions:
            # Check if any new position opened within 15 minutes of loss_pos closing
            for next_pos in sorted_positions:
                if next_pos.position_id == loss_pos.position_id:
                    continue

                time_diff = (next_pos.open_timestamp - loss_pos.close_timestamp).total_seconds() / 60.0
                if 0.0 <= time_diff <= 15.0:
                    revenge_count += 1
                    revenge_details.append({
                        "losing_symbol": loss_pos.symbol,
                        "next_symbol": next_pos.symbol,
                        "time_gap_minutes": round(time_diff, 1),
                        "loss_amount": loss_pos.realized_pnl,
                    })
                    break

        if revenge_count > 0:
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.MISTAKE,
                    title="Revenge Trading Detected",
                    description=(
                        f"Detected {revenge_count} instance(s) of re-entering trades within "
                        "15 minutes of closing a losing position."
                    ),
                    severity=Severity.CRITICAL,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "revenge_trades_count": revenge_count,
                        "losing_positions_count": metrics.losing_positions_count,
                        "details": revenge_details,
                    },
                    coaching_message=(
                        "You executed new trades immediately after suffering a loss. Emotional "
                        "re-entries often lead to compounding losses. Take a mandatory 15-minute "
                        "breather after any losing trade to reset your mindset."
                    ),
                    action_item="Institute a strict 15-minute cooling-off period after closing any losing trade.",
                ),
            )

        return RuleResult(is_triggered=False)


class FOMOBuyingRule(BaseRule):
    """Rule 2: Detects FOMO buying (purchasing near intraday/recent highs or chasing spikes)."""

    @property
    def rule_id(self) -> str:
        return "MISTAKE_FOMO_BUYING"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        if not closed_positions:
            return RuleResult(is_triggered=False)

        # Flag positions where buy price was significantly higher than recent average entry
        fomo_positions = []
        for pos in closed_positions:
            # High buy price variance within position chunks or rapid entry
            if pos.realized_pnl_percent < -3.0 and pos.holding_duration_minutes < 30.0:
                fomo_positions.append(pos)

        fomo_count = len(fomo_positions)
        if fomo_count >= 2 or (metrics.closed_positions_count > 0 and (fomo_count / metrics.closed_positions_count) > 0.25):
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.MISTAKE,
                    title="FOMO Momentum Chasing",
                    description=(
                        f"Identified {fomo_count} position(s) entered during momentum spikes "
                        "that resulted in rapid losses."
                    ),
                    severity=Severity.HIGH,
                    confidence=Confidence.MEDIUM,
                    metrics_context={
                        "fomo_positions_count": fomo_count,
                        "total_positions_count": metrics.closed_positions_count,
                    },
                    coaching_message=(
                        "Buying extended stocks at intraday peaks often leads to immediate drawdown. "
                        "Avoid buying market orders on green spikes; wait for healthy pullbacks."
                    ),
                    action_item="Use limit orders below market price instead of market orders on momentum candles.",
                ),
            )

        return RuleResult(is_triggered=False)


class PositionSizingRule(BaseRule):
    """Rule 3: Evaluates position sizing discipline against portfolio allocation caps."""

    @property
    def rule_id(self) -> str:
        return "RISK_POSITION_SIZING"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        max_sizing = metrics.max_position_sizing_pct

        if max_sizing > 15.0:
            severity = Severity.CRITICAL if max_sizing > 25.0 else Severity.MEDIUM
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.RISK_WARNING,
                    title="Oversized Position Allocation",
                    description=f"Single position allocation reached {max_sizing:.1f}% of total portfolio capital.",
                    severity=severity,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "max_position_sizing_pct": max_sizing,
                        "avg_position_sizing_pct": metrics.avg_position_sizing_pct,
                    },
                    coaching_message=(
                        f"Your largest position constitutes {max_sizing:.1f}% of your portfolio. "
                        "Concentrating too much capital in a single stock exposes your portfolio to severe drawdown."
                    ),
                    action_item="Cap single-stock allocation to 5-10% of total portfolio net worth.",
                ),
            )

        return RuleResult(is_triggered=False)


class HoldingDurationAsymmetryRule(BaseRule):
    """Rule 4: Detects holding duration asymmetry (holding losing trades much longer than winners)."""

    @property
    def rule_id(self) -> str:
        return "MISTAKE_HOLDING_DURATION_ASYMMETRY"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        if metrics.winning_positions_count == 0 or metrics.losing_positions_count == 0:
            return RuleResult(is_triggered=False)

        ratio = metrics.holding_duration_ratio

        if ratio > 1.5:
            if ratio > 3.0:
                severity = Severity.CRITICAL
            elif ratio > 2.0:
                severity = Severity.HIGH
            else:
                severity = Severity.MEDIUM

            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.MISTAKE,
                    title="Holding Losing Positions Too Long",
                    description=(
                        f"You hold losing positions for an average of {metrics.avg_losing_duration_minutes:.1f} mins, "
                        f"which is {ratio:.1f}x longer than your winning positions ({metrics.avg_winning_duration_minutes:.1f} mins)."
                    ),
                    severity=severity,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "holding_duration_ratio": ratio,
                        "avg_losing_duration_minutes": metrics.avg_losing_duration_minutes,
                        "avg_winning_duration_minutes": metrics.avg_winning_duration_minutes,
                    },
                    coaching_message=(
                        f"You hold losing trades {ratio:.1f}x longer than winners. "
                        "Classic trader bias is hoping losers come back while cutting winners early. "
                        "Cut losses decisively and let your winners run."
                    ),
                    action_item="Set a hard time-stop or price stop-loss to exit non-performing trades promptly.",
                ),
            )

        return RuleResult(is_triggered=False)


class RiskRewardRatioRule(BaseRule):
    """Rule 5: Evaluates Risk-Reward Ratio (RRR) for sub-optimal risk management or strong execution."""

    @property
    def rule_id(self) -> str:
        return "RISK_REWARD_RATIO"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        if metrics.closed_positions_count < 2 or metrics.losing_positions_count == 0:
            return RuleResult(is_triggered=False)

        rrr = metrics.risk_reward_ratio

        if rrr < 1.0:
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.MISTAKE,
                    title="Sub-optimal Risk-Reward Ratio",
                    description=(
                        f"Your average win (₹{metrics.average_profit:.2f}) is smaller than your "
                        f"average loss (₹{metrics.average_loss:.2f}), giving RRR of {rrr:.2f}."
                    ),
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "risk_reward_ratio": rrr,
                        "average_profit": metrics.average_profit,
                        "average_loss": metrics.average_loss,
                    },
                    coaching_message=(
                        f"Your average loss (₹{metrics.average_loss:.2f}) exceeds your average win "
                        f"(₹{metrics.average_profit:.2f}). This requires an extremely high win rate to stay profitable. "
                        "Aim for at least a 1.5:1 profit-to-loss target on entries."
                    ),
                    action_item="Target trades with at least 1.5x potential upside relative to your stop-loss distance.",
                ),
            )
        elif rrr >= 2.0:
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.STRENGTH,
                    title="Excellent Risk-Reward Ratio",
                    description=f"Maintained strong RRR of {rrr:.2f} across closed trades.",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "risk_reward_ratio": rrr,
                        "average_profit": metrics.average_profit,
                        "average_loss": metrics.average_loss,
                    },
                    coaching_message=(
                        f"Outstanding execution! Your average profit (₹{metrics.average_profit:.2f}) is "
                        f"{rrr:.2f}x your average loss (₹{metrics.average_loss:.2f}). This provides a strong statistical edge."
                    ),
                    action_item="Maintain your current disciplined risk-to-reward entry criteria.",
                ),
            )

        return RuleResult(is_triggered=False)


class ConcentrationRiskRule(BaseRule):
    """Rule 6: Evaluates portfolio concentration risk using the Herfindahl-Hirschman Index (HHI)."""

    @property
    def rule_id(self) -> str:
        return "RISK_CONCENTRATION_HHI"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        hhi = metrics.portfolio_concentration_hhi

        if hhi > 1800.0:
            severity = Severity.HIGH if hhi > 3000.0 else Severity.MEDIUM
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.RISK_WARNING,
                    title="High Portfolio Concentration",
                    description=f"Portfolio concentration index (HHI) is high at {hhi:.0f}.",
                    severity=severity,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "portfolio_concentration_hhi": hhi,
                    },
                    coaching_message=(
                        f"Your portfolio concentration index is {hhi:.0f} (values > 1,800 indicate high concentration). "
                        "Spreading capital across multiple holdings protects you against stock-specific shocks."
                    ),
                    action_item="Diversify holdings across at least 4-6 non-correlated assets or sectors.",
                ),
            )

        return RuleResult(is_triggered=False)


class OvertradingRule(BaseRule):
    """Rule 7: Detects overtrading and excessive trade execution frequency."""

    @property
    def rule_id(self) -> str:
        return "MISTAKE_OVERTRADING"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        trade_count = metrics.total_trades_count

        if trade_count > 10:
            severity = Severity.HIGH if trade_count > 15 else Severity.MEDIUM
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.MISTAKE,
                    title="Overtrading Frequency Alert",
                    description=f"Executed {trade_count} raw trades in the current evaluation session.",
                    severity=severity,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "total_trades_count": trade_count,
                        "closed_positions_count": metrics.closed_positions_count,
                    },
                    coaching_message=(
                        f"You executed {trade_count} trades. Overtrading increases transaction costs, "
                        "induces mental fatigue, and usually lowers trade selection quality."
                    ),
                    action_item="Set a maximum daily trade limit (e.g. 3-5 high-quality trades per day).",
                ),
            )

        return RuleResult(is_triggered=False)


class DrawdownRule(BaseRule):
    """Rule 8: Monitors capital drawdown from peak portfolio equity."""

    @property
    def rule_id(self) -> str:
        return "RISK_MAX_DRAWDOWN"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        dd_pct = metrics.max_drawdown_pct

        if dd_pct > 10.0:
            severity = Severity.CRITICAL if dd_pct > 20.0 else Severity.HIGH
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.RISK_WARNING,
                    title="Severe Capital Drawdown",
                    description=f"Maximum portfolio drawdown reached {dd_pct:.1f}% (₹{metrics.max_drawdown_amount:.2f}).",
                    severity=severity,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "max_drawdown_pct": dd_pct,
                        "max_drawdown_amount": metrics.max_drawdown_amount,
                    },
                    coaching_message=(
                        f"Your portfolio experienced a peak-to-trough drawdown of {dd_pct:.1f}%. "
                        "Protecting remaining capital is critical. Reduce trade position sizing until performance stabilizes."
                    ),
                    action_item="Reduce trade sizing by 50% until equity curve recovers.",
                ),
            )

        return RuleResult(is_triggered=False)


class StopLossDisciplineRule(BaseRule):
    """Rule 9: Detects unmanaged large losses (> -5%) indicating failure to honor stop-loss."""

    @property
    def rule_id(self) -> str:
        return "MISTAKE_STOP_LOSS_DISCIPLINE"

    def evaluate(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> RuleResult:
        if not closed_positions:
            return RuleResult(is_triggered=False)

        unmanaged_losses = [p for p in closed_positions if p.is_loss and p.realized_pnl_percent < -5.0]
        unmanaged_count = len(unmanaged_losses)

        if unmanaged_count > 0:
            severity = Severity.CRITICAL if unmanaged_count >= 2 else Severity.HIGH
            return RuleResult(
                is_triggered=True,
                insight=Insight(
                    rule_id=self.rule_id,
                    category=InsightCategory.MISTAKE,
                    title="Unmanaged Large Losses Detected",
                    description=f"Identified {unmanaged_count} losing position(s) with losses exceeding -5.0%.",
                    severity=severity,
                    confidence=Confidence.HIGH,
                    metrics_context={
                        "unmanaged_losses_count": unmanaged_count,
                        "worst_loss_pct": min(p.realized_pnl_percent for p in unmanaged_losses),
                    },
                    coaching_message=(
                        f"You had {unmanaged_count} trade(s) with losses worse than -5.0%. "
                        "Allowing losses to run deep destroys long-term expectancy. Always respect your stop-loss."
                    ),
                    action_item="Set an explicit stop-loss order immediately upon position entry.",
                ),
            )

        return RuleResult(is_triggered=False)


class RuleEngine:
    """
    Orchestrates execution of all modular rules and returns prioritized insights.
    """

    SEVERITY_ORDER = {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
    }

    CATEGORY_ORDER = {
        InsightCategory.RISK_WARNING: 3,
        InsightCategory.MISTAKE: 2,
        InsightCategory.HABIT: 1,
        InsightCategory.STRENGTH: 0,
    }

    def __init__(self, rules: Optional[List[BaseRule]] = None):
        """Initializes RuleEngine with a default or custom list of rules."""
        self.rules: List[BaseRule] = rules if rules is not None else self._get_default_rules()

    @staticmethod
    def _get_default_rules() -> List[BaseRule]:
        """Instantiates all 9 default rules."""
        return [
            RevengeTradingRule(),
            FOMOBuyingRule(),
            PositionSizingRule(),
            HoldingDurationAsymmetryRule(),
            RiskRewardRatioRule(),
            ConcentrationRiskRule(),
            OvertradingRule(),
            DrawdownRule(),
            StopLossDisciplineRule(),
        ]

    def evaluate_all(
        self,
        metrics: AnalyticsMetrics,
        closed_positions: Optional[List[ClosedPosition]] = None,
        holdings: Optional[List[HoldingItem]] = None,
        raw_trades: Optional[List[TradeInput]] = None,
    ) -> List[Insight]:
        """
        Runs all registered rules against metrics and trade context.

        Returns:
            List of triggered Insight objects prioritized by Severity (CRITICAL first) and Category.
        """
        insights: List[Insight] = []

        for rule in self.rules:
            result = rule.evaluate(
                metrics=metrics,
                closed_positions=closed_positions,
                holdings=holdings,
                raw_trades=raw_trades,
            )
            if result.is_triggered and result.insight:
                insights.append(result.insight)

        # Sort insights by Severity descending, then Category descending
        insights.sort(
            key=lambda item: (
                self.SEVERITY_ORDER.get(item.severity, 0),
                self.CATEGORY_ORDER.get(item.category, 0),
            ),
            reverse=True,
        )

        return insights
