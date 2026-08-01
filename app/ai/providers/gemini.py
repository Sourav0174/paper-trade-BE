"""
Google Gemini provider implementation using official google-genai Python SDK.
"""

from typing import Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.ai.exceptions import (
    AIConfigurationError,
    AIException,
    AIRateLimitError,
    AIResponseParsingError,
    AIServiceUnavailableError,
)
from app.ai.providers.base import BaseAIProvider
from app.ai.settings import AISettings, get_ai_settings


class GeminiProvider(BaseAIProvider):
    """Concrete AI provider implementation using official google-genai Python SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        settings: Optional[AISettings] = None,
    ):
        cfg = settings or get_ai_settings()
        self.api_key = api_key or cfg.effective_gemini_api_key
        self.model_name = model_name or cfg.GEMINI_MODEL
        self.timeout_seconds = timeout_seconds or cfg.GEMINI_TIMEOUT_SECONDS

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        if not self.api_key:
            raise AIConfigurationError("Gemini API key is not configured")

        try:
            http_opts = types.HttpOptions(timeout=float(self.timeout_seconds))
            client = genai.Client(api_key=self.api_key, http_options=http_opts)

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
            )
            if response_mime_type:
                config.response_mime_type = response_mime_type

            response = client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )

            text = response.text
            if not text:
                raise AIResponseParsingError("Gemini SDK returned empty response text")

            return text.strip()

        except APIError as e:
            code = getattr(e, "code", None) or getattr(e, "status_code", None)
            message = str(e)

            if code == 429 or "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
                raise AIRateLimitError(f"Gemini quota or rate limit exceeded: {e}") from e
            if code in (400, 401, 403) or "API_KEY_INVALID" in message or "invalid" in message.lower():
                raise AIConfigurationError(f"Gemini authentication or client error: {e}") from e
            if code and code >= 500:
                raise AIServiceUnavailableError(f"Gemini server error ({code}): {e}") from e

            raise AIException(f"Gemini API error ({code}): {e}") from e

        except (AIException, Exception) as e:
            if isinstance(e, AIException):
                raise
            err_msg = str(e).lower()
            if "timeout" in err_msg or "timed out" in err_msg:
                raise AIServiceUnavailableError(f"Gemini request timed out: {e}") from e
            if "api key" in err_msg or "auth" in err_msg:
                raise AIConfigurationError(f"Gemini configuration error: {e}") from e

            raise AIException(f"Gemini SDK execution failed: {e}") from e
