"""
Insight Prioritizer and Mentor Summary Generator.

Calculates Trading Health Score, maps performance grades, deduplicates/merges insights,
selects a single primary improvement focus, and generates prioritized action items.

Operates deterministically without using AI or external services.
"""

from typing import Dict, List, Optional, Set
from app.mentor.schema import (
    AnalyticsMetrics,
    Confidence,
    Insight,
    InsightCategory,
    MentorSummary,
    Severity,
    TradingGrade,
)


class InsightPrioritizer:
    """
    Deterministic Insight Prioritizer and Summary Generator.
    """

    SEVERITY_WEIGHTS = {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
    }

    CONFIDENCE_WEIGHTS = {
        Confidence.HIGH: 3,
        Confidence.MEDIUM: 2,
        Confidence.LOW: 1,
    }

    CATEGORY_WEIGHTS = {
        InsightCategory.RISK_WARNING: 4,
        InsightCategory.MISTAKE: 3,
        InsightCategory.HABIT: 2,
        InsightCategory.STRENGTH: 1,
    }

    @classmethod
    def prioritize(
        cls,
        metrics: AnalyticsMetrics,
        insights: List[Insight],
    ) -> MentorSummary:
        """
        Generates a consolidated MentorSummary from analytics metrics and raw insights.

        Args:
            metrics: AnalyticsMetrics instance.
            insights: List of raw triggered Insight objects from RuleEngine.

        Returns:
            MentorSummary populated with health score, grade, merged insights, and action items.
        """
        merged_insights = cls._merge_related_insights(insights)
        ranked_insights = cls._rank_insights(merged_insights)

        health_score, sub_scores = cls.calculate_health_score(metrics, raw_insights=insights)
        grade = cls.calculate_grade(health_score)

        top_strengths = [i for i in ranked_insights if i.category == InsightCategory.STRENGTH][:3]
        top_mistakes = [i for i in ranked_insights if i.category == InsightCategory.MISTAKE][:3]
        top_risks = [i for i in ranked_insights if i.category == InsightCategory.RISK_WARNING][:3]

        action_items = cls.generate_action_items(ranked_insights)
        improvement_focus = cls.determine_improvement_focus(metrics, raw_insights=insights)

        portfolio_summary = {
            "trading_health_score": health_score,
            "win_rate_pct": metrics.win_rate_pct,
            "profit_factor": metrics.profit_factor,
            "risk_reward_ratio": metrics.risk_reward_ratio,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "holding_duration_ratio": metrics.holding_duration_ratio,
            "max_position_sizing_pct": metrics.max_position_sizing_pct,
            "portfolio_concentration_hhi": metrics.portfolio_concentration_hhi,
            "total_realized_pnl": metrics.total_realized_pnl,
            "total_trades_count": metrics.total_trades_count,
            "closed_positions_count": metrics.closed_positions_count,
            "sub_scores": sub_scores,
        }

        return MentorSummary(
            trading_health_score=health_score,
            grade=grade,
            portfolio_summary=portfolio_summary,
            top_strengths=top_strengths,
            top_mistakes=top_mistakes,
            top_risks=top_risks,
            action_items=action_items,
            improvement_focus=improvement_focus,
            all_insights=ranked_insights,
        )

    @classmethod
    def calculate_health_score(
        cls,
        metrics: AnalyticsMetrics,
        raw_insights: List[Insight],
    ) -> tuple[float, Dict[str, float]]:
        """
        Calculates Trading Health Score (0.0 to 100.0) based on weighted sub-scores and penalties.

        Returns:
            Tuple of (final_health_score, sub_scores_dict)
        """
        rule_ids = {i.rule_id for i in raw_insights}

        # 1. Risk Management Sub-Score (25% Weight)
        sub_risk = 100.0
        if "MISTAKE_STOP_LOSS_DISCIPLINE" in rule_ids:
            sub_risk -= 30.0
        if "RISK_POSITION_SIZING" in rule_ids:
            sub_risk -= 25.0
        if "RISK_REWARD_RATIO" in rule_ids and any(i.rule_id == "RISK_REWARD_RATIO" and i.category == InsightCategory.MISTAKE for i in raw_insights):
            sub_risk -= 20.0
        sub_risk = max(0.0, sub_risk)

        # 2. Execution Discipline Sub-Score (25% Weight)
        sub_discipline = 100.0
        if "MISTAKE_REVENGE_TRADING" in rule_ids:
            sub_discipline -= 35.0
        if "MISTAKE_FOMO_BUYING" in rule_ids:
            sub_discipline -= 25.0
        if "MISTAKE_OVERTRADING" in rule_ids:
            sub_discipline -= 20.0
        if "MISTAKE_HOLDING_DURATION_ASYMMETRY" in rule_ids:
            sub_discipline -= 20.0
        sub_discipline = max(0.0, sub_discipline)

        # 3. Profitability Sub-Score (20% Weight)
        win_part = metrics.win_rate_pct * 0.6
        pf_part = min(metrics.profit_factor, 3.0) * 13.33
        sub_profitability = min(100.0, win_part + pf_part)

        # 4. Capital Preservation Sub-Score (15% Weight)
        sub_preservation = max(0.0, 100.0 - (metrics.max_drawdown_pct * 4.0))

        # 5. Diversification Sub-Score (15% Weight)
        hhi_excess = max(0.0, metrics.portfolio_concentration_hhi - 1000.0)
        sub_diversification = max(0.0, 100.0 - (hhi_excess * 0.03))

        # Weighted base score
        base_score = (
            0.25 * sub_risk +
            0.25 * sub_discipline +
            0.20 * sub_profitability +
            0.15 * sub_preservation +
            0.15 * sub_diversification
        )

        # Critical Penalty Deductions
        penalties = 0.0
        if "MISTAKE_REVENGE_TRADING" in rule_ids:
            penalties += 15.0
        if metrics.max_position_sizing_pct > 25.0:
            penalties += 10.0
        if metrics.max_drawdown_pct > 20.0:
            penalties += 15.0

        final_score = round(max(0.0, min(100.0, base_score - penalties)), 1)

        sub_scores = {
            "risk_management": round(sub_risk, 1),
            "execution_discipline": round(sub_discipline, 1),
            "profitability": round(sub_profitability, 1),
            "capital_preservation": round(sub_preservation, 1),
            "diversification": round(sub_diversification, 1),
        }

        return final_score, sub_scores

    @staticmethod
    def calculate_grade(health_score: float) -> TradingGrade:
        """Maps Trading Health Score to performance TradingGrade enum."""
        if health_score >= 90.0:
            return TradingGrade.MASTER
        if health_score >= 75.0:
            return TradingGrade.DISCIPLINED
        if health_score >= 60.0:
            return TradingGrade.AVERAGE
        if health_score >= 40.0:
            return TradingGrade.NEEDS_WORK
        return TradingGrade.HIGH_RISK

    @classmethod
    def _merge_related_insights(cls, insights: List[Insight]) -> List[Insight]:
        """Merges related overlapping insights into unified recommendations to avoid advice duplication."""
        rule_ids = {i.rule_id for i in insights}

        # Check if both Position Sizing and Concentration Risk exist
        if "RISK_POSITION_SIZING" in rule_ids and "RISK_CONCENTRATION_HHI" in rule_ids:
            sizing_insight = next(i for i in insights if i.rule_id == "RISK_POSITION_SIZING")
            hhi_insight = next(i for i in insights if i.rule_id == "RISK_CONCENTRATION_HHI")

            merged_severity = (
                sizing_insight.severity
                if cls.SEVERITY_WEIGHTS.get(sizing_insight.severity, 0) >= cls.SEVERITY_WEIGHTS.get(hhi_insight.severity, 0)
                else hhi_insight.severity
            )

            merged = Insight(
                rule_id="RISK_POSITION_AND_DIVERSIFICATION",
                category=InsightCategory.RISK_WARNING,
                title="Position Sizing & Concentration Risk",
                description="Single position sizes exceed allocation limits and portfolio capital is concentrated in few holdings.",
                severity=merged_severity,
                confidence=Confidence.HIGH,
                metrics_context={
                    "max_position_sizing_pct": sizing_insight.metrics_context.get("max_position_sizing_pct"),
                    "portfolio_concentration_hhi": hhi_insight.metrics_context.get("portfolio_concentration_hhi"),
                },
            )

            # Filter out individual sizing and hhi insights, add merged insight
            filtered = [i for i in insights if i.rule_id not in ("RISK_POSITION_SIZING", "RISK_CONCENTRATION_HHI")]
            filtered.append(merged)
            return filtered

        return list(insights)

    @classmethod
    def _rank_insights(cls, insights: List[Insight]) -> List[Insight]:
        """Sorts insights by Severity, Confidence, and Category weights descending."""
        sorted_insights = list(insights)
        sorted_insights.sort(
            key=lambda item: (
                cls.SEVERITY_WEIGHTS.get(item.severity, 0),
                cls.CONFIDENCE_WEIGHTS.get(item.confidence, 0),
                cls.CATEGORY_WEIGHTS.get(item.category, 0),
            ),
            reverse=True,
        )
        return sorted_insights

    @classmethod
    def generate_action_items(cls, ranked_insights: List[Insight]) -> List[str]:
        """Extracts up to 3 concrete prioritized action item strings from top insights."""
        action_items: List[str] = []
        seen_items: Set[str] = set()

        for insight in ranked_insights:
            item = insight.action_item.strip()
            if item and item not in seen_items:
                seen_items.add(item)
                action_items.append(item)
                if len(action_items) == 3:
                    break

        return action_items

    @classmethod
    def determine_improvement_focus(
        cls,
        metrics: AnalyticsMetrics,
        raw_insights: List[Insight],
    ) -> str:
        """Determines exactly ONE primary coaching improvement focus area for the user."""
        rule_ids = {i.rule_id for i in raw_insights}

        if "MISTAKE_REVENGE_TRADING" in rule_ids or "MISTAKE_FOMO_BUYING" in rule_ids:
            return "Emotional Trading"

        if "RISK_MAX_DRAWDOWN" in rule_ids or "MISTAKE_STOP_LOSS_DISCIPLINE" in rule_ids:
            return "Risk Management"

        if "RISK_POSITION_SIZING" in rule_ids or "RISK_POSITION_AND_DIVERSIFICATION" in rule_ids:
            return "Position Sizing"

        if "RISK_CONCENTRATION_HHI" in rule_ids:
            return "Diversification"

        if "MISTAKE_HOLDING_DURATION_ASYMMETRY" in rule_ids or "MISTAKE_OVERTRADING" in rule_ids:
            return "Discipline"

        if metrics.win_rate_pct < 50.0 or metrics.profit_factor < 1.2:
            return "Profit Protection"

        return "Discipline"
