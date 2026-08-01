"""
Template Fallback Response Generator.

Produces a structured MentorResponse deterministically without using AI.
Used when LLM APIs are offline, unconfigured, or fail validation guardrails.
"""

from app.mentor.schema import MentorResponse, MentorSummary, TradingGrade


class TemplateGenerator:
    """
    Deterministic template fallback generator for MentorResponse.
    """

    HEADLINES = {
        TradingGrade.MASTER: "Outstanding Execution & Masterful Discipline!",
        TradingGrade.DISCIPLINED: "Solid Performance & Disciplined Execution",
        TradingGrade.AVERAGE: "Steady Performance with Opportunities for Growth",
        TradingGrade.NEEDS_WORK: "Refine Risk Control & Execution Discipline",
        TradingGrade.HIGH_RISK: "Immediate Capital Preservation & Risk Reset Required",
    }

    MOTIVATIONS = {
        TradingGrade.MASTER: "Keep honoring your trading plan and maintaining your edge.",
        TradingGrade.DISCIPLINED: "Consistency is built trade by trade—stay focused on your rules.",
        TradingGrade.AVERAGE: "Small adjustments to risk and discipline will unlock your next level.",
        TradingGrade.NEEDS_WORK: "Protecting your capital today creates the foundation for future profits.",
        TradingGrade.HIGH_RISK: "Reset your emotional state, scale back position sizes, and protect your capital.",
    }

    @classmethod
    def generate_response(cls, summary: MentorSummary) -> MentorResponse:
        """
        Generates a structured MentorResponse directly from MentorSummary.
        """
        headline = cls.HEADLINES.get(summary.grade, "Trading Performance Review")
        motivation = cls.MOTIVATIONS.get(summary.grade, "Focus on disciplined execution.")

        overview_summary = (
            f"Your trading health score is {summary.trading_health_score:.1f}/100 ({summary.grade.value}). "
            f"Across {summary.portfolio_summary.get('closed_positions_count', 0)} closed position(s), "
            f"you achieved a win rate of {summary.portfolio_summary.get('win_rate_pct', 0.0):.1f}%."
        )

        strengths = [s.title for s in summary.top_strengths] if summary.top_strengths else ["Maintained active position management"]
        mistakes = [m.title for m in summary.top_mistakes]
        risk_warning = summary.top_risks[0].title if summary.top_risks else None
        action_items = summary.action_items if summary.action_items else ["Review position sizing before placing new orders."]

        return MentorResponse(
            headline=headline,
            summary=overview_summary,
            strengths=strengths,
            mistakes=mistakes,
            risk_warning=risk_warning,
            action_items=action_items,
            motivation=motivation,
            next_focus=summary.improvement_focus,
        )
