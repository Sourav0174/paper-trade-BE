"""
Response Guardrail Validator for AI Mentor.

Validates generated mentor responses against strict legal and financial guardrails.
Rejects price predictions, buy/sell recommendations, profit guarantees, and markdown formatting.
"""

import re
from typing import List
from pydantic import BaseModel, Field
from app.mentor.schema import MentorResponse


class ValidationResult(BaseModel):
    """Container for response validation status and detected violations."""

    is_valid: bool = Field(description="True if response passes all guardrails")
    violations: List[str] = Field(default_factory=list, description="List of detected guardrail violations")


class ResponseValidator:
    """
    Financial and legal guardrail validator for generated mentor coaching responses.
    """

    BUY_PATTERNS = [
        r"\bbuy\b\s+(?:this|stock|[A-Z]+)",
        r"\bpurchase\b\s+(?:shares|stock|[A-Z]+)",
        r"\baccumulate\b\s+(?:shares|stock|[A-Z]+)",
        r"\bgo long on\b",
        r"\brecommend buying\b",
    ]

    SELL_PATTERNS = [
        r"\bsell\b\s+(?:this|stock|[A-Z]+)",
        r"\bdump\b\s+(?:shares|stock|[A-Z]+)",
        r"\bexit position in\b\s+[A-Z]+",
        r"\bshort sell\b",
        r"\brecommend selling\b",
    ]

    PREDICTION_PATTERNS = [
        r"\bprice target\b",
        r"\bwill reach\b",
        r"\bpredicted price\b",
        r"\bgoing to\b\s+\d+",
        r"\bstock will\b\s+(?:rise|fall|rally|crash)",
        r"\bexpected target\b",
    ]

    GUARANTEE_PATTERNS = [
        r"\bguaranteed profit\b",
        r"\bguaranteed return\b",
        r"\brisk-free\b",
        r"\b100%\s+gain\b",
        r"\b100%\s+profit\b",
    ]

    MARKDOWN_PATTERNS = [
        r"```",
        r"^#+\s",
    ]

    @classmethod
    def validate(cls, response: MentorResponse) -> ValidationResult:
        """
        Validates all text fields of a MentorResponse object against guardrails.
        """
        violations: List[str] = []

        combined_text = " ".join([
            response.headline,
            response.summary,
            " ".join(response.strengths),
            " ".join(response.mistakes),
            response.risk_warning or "",
            " ".join(response.action_items),
            response.motivation,
            response.next_focus,
        ]).lower()

        cls._check_patterns(combined_text, cls.BUY_PATTERNS, "Buy recommendation detected", violations)
        cls._check_patterns(combined_text, cls.SELL_PATTERNS, "Sell recommendation detected", violations)
        cls._check_patterns(combined_text, cls.PREDICTION_PATTERNS, "Price prediction detected", violations)
        cls._check_patterns(combined_text, cls.GUARANTEE_PATTERNS, "Profit guarantee detected", violations)
        cls._check_patterns(combined_text, cls.MARKDOWN_PATTERNS, "Markdown formatting detected", violations)

        return ValidationResult(
            is_valid=len(violations) == 0,
            violations=violations,
        )

    @staticmethod
    def _check_patterns(text: str, patterns: List[str], error_label: str, violations: List[str]) -> None:
        """Helper to match regex patterns against combined text."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                violations.append(f"{error_label}: '{pattern}'")
                break
