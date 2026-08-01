"""
Mentor Response Generator Interface and Implementations.

Defines abstract BaseMentorGenerator, concrete GeminiGenerator delegating to AIClient infrastructure,
and seamless fallback to TemplateGenerator.
"""

from abc import ABC, abstractmethod
import json
import logging
from typing import Optional

from app.ai import AIClient, AIException, GeminiProvider
from app.mentor.prompt_builder import PromptBuilder
from app.mentor.response_validator import ResponseValidator
from app.mentor.schema import MentorResponse, MentorSummary, PromptContext
from app.mentor.template_generator import TemplateGenerator

logger = logging.getLogger(__name__)


class BaseMentorGenerator(ABC):
    """Abstract interface for all mentor response generators."""

    @abstractmethod
    def generate(self, context: PromptContext, summary: MentorSummary) -> MentorResponse:
        """
        Generates a structured MentorResponse from PromptContext and MentorSummary.
        """
        pass


class GeminiGenerator(BaseMentorGenerator):
    """
    LLM generator delegating HTTP and provider details to AIClient with guardrail validation and template fallback.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        ai_client: Optional[AIClient] = None,
    ):
        if ai_client:
            self.ai_client = ai_client
        else:
            provider = GeminiProvider(
                api_key=api_key,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
            )
            self.ai_client = AIClient(provider=provider)

    def generate(self, context: PromptContext, summary: MentorSummary) -> MentorResponse:
        """
        Attempts LLM synthesis via AIClient, validates response, and falls back to TemplateGenerator on failure.
        """
        try:
            raw_json_str = self.ai_client.generate(
                system_prompt=context.system_prompt,
                user_prompt=context.user_prompt,
                response_mime_type="application/json",
            )
            parsed_dict = json.loads(raw_json_str)

            response = MentorResponse(
                headline=str(parsed_dict.get("headline", "")),
                summary=str(parsed_dict.get("summary", "")),
                strengths=list(parsed_dict.get("strengths", [])),
                mistakes=list(parsed_dict.get("mistakes", [])),
                risk_warning=parsed_dict.get("risk_warning"),
                action_items=list(parsed_dict.get("action_items", [])),
                motivation=str(parsed_dict.get("motivation", "")),
                next_focus=str(parsed_dict.get("next_focus", summary.improvement_focus)),
            )

            validation = ResponseValidator.validate(response)
            if not validation.is_valid:
                logger.warning("LLM response failed guardrail validation: %s. Reverting to TemplateGenerator.", validation.violations)
                return TemplateGenerator.generate_response(summary)

            return response

        except (AIException, Exception) as e:
            logger.info("AI generation unavailable or failed (%s). Reverting to TemplateGenerator.", e)
            return TemplateGenerator.generate_response(summary)


class MentorGenerator:
    """
    High-level facade orchestrating PromptBuilder, BaseMentorGenerator, and TemplateGenerator.
    """

    def __init__(self, generator: Optional[BaseMentorGenerator] = None):
        self.generator = generator or GeminiGenerator()

    def generate(self, summary: MentorSummary) -> MentorResponse:
        """
        Orchestrates full prompt building, LLM generation, validation, and template fallback.
        """
        context = PromptBuilder.build_prompt_context(summary)
        return self.generator.generate(context, summary)
