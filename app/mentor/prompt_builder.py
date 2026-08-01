"""
Prompt Builder for AI Mentor.

Converts a MentorSummary object into a decoupled PromptContext container.
Does not depend on any specific LLM provider implementation.
"""

import json
from app.mentor.schema import MentorSummary, PromptContext


class PromptBuilder:
    """
    Constructs system and user prompts for LLM synthesis while enforcing strict guardrails.
    """

    SYSTEM_PROMPT = """YOU ARE AN ELITE TRADING MENTOR & BEHAVIORAL COACH FOR PAPERTRADE.

CRITICAL FINANCIAL & LEGAL GUARDRAILS:
1. NEVER PREDICT FUTURE STOCK PRICES OR MARKET TRENDS.
2. NEVER RECOMMEND BUYING, SELLING, OR HOLDING ANY SPECIFIC STOCK.
3. NEVER PROMISE PROFITS OR GUARANTEE RETURNS.
4. FOCUS EXCLUSIVELY ON TRADING DISCIPLINE, RISK MANAGEMENT, BEHAVIORAL PATTERNS, POSITION SIZING, AND STATISTICAL PERFORMANCE.
5. ADAPT A CONSTRUCTIVE, ENCOURAGING, PROFESSIONAL COACHING TONE.

OUTPUT FORMAT INSTRUCTION:
YOU MUST RESPOND ONLY WITH A VALID JSON OBJECT MATCHING THIS EXACT SCHEMA:
{
  "headline": "Short encouraging headline",
  "summary": "2-3 sentence overview of trading discipline and performance",
  "strengths": ["Strength 1", "Strength 2"],
  "mistakes": ["Mistake 1", "Mistake 2"],
  "risk_warning": "Primary risk alert or null",
  "action_items": ["Action 1", "Action 2"],
  "motivation": "Motivational closing advice",
  "next_focus": "Single primary focus area"
}
DO NOT INCLUDE MARKDOWN FORMATTING OR EXTRA TEXT OUTSIDE THE JSON OBJECT."""

    @classmethod
    def build_prompt_context(cls, summary: MentorSummary) -> PromptContext:
        """
        Builds a PromptContext containing system instructions and JSON user data payload.
        """
        user_payload = {
            "health_score": summary.trading_health_score,
            "grade": summary.grade.value,
            "improvement_focus": summary.improvement_focus,
            "portfolio_summary": summary.portfolio_summary,
            "top_strengths": [
                {
                    "rule_id": s.rule_id,
                    "title": s.title,
                    "description": s.description,
                    "coaching": s.coaching_message,
                }
                for s in summary.top_strengths
            ],
            "top_mistakes": [
                {
                    "rule_id": m.rule_id,
                    "title": m.title,
                    "description": m.description,
                    "coaching": m.coaching_message,
                    "severity": m.severity.value,
                }
                for m in summary.top_mistakes
            ],
            "top_risks": [
                {
                    "rule_id": r.rule_id,
                    "title": r.title,
                    "description": r.description,
                    "coaching": r.coaching_message,
                    "severity": r.severity.value,
                }
                for r in summary.top_risks
            ],
            "action_items": summary.action_items,
        }

        user_prompt = f"Analyze the following deterministic mentor summary data and return the structured JSON coaching response:\n\n{json.dumps(user_payload, indent=2)}"

        return PromptContext(
            system_prompt=cls.SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
