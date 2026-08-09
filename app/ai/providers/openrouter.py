"""
OpenRouter provider implementation using the official OpenAI Python SDK
(OpenRouter exposes an OpenAI-compatible API).
"""

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Optional
from openai import AsyncOpenAI, OpenAI
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
)

from app.ai.exceptions import (
    AIConfigurationError,
    AIException,
    AIRateLimitError,
    AIResponseParsingError,
    AIServiceUnavailableError,
)
from app.ai.providers.base import BaseAIProvider
from app.ai.settings import AISettings, get_ai_settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(BaseAIProvider):
    """Concrete AI provider implementation using OpenRouter's OpenAI-compatible API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        settings: Optional[AISettings] = None,
    ):
        cfg = settings or get_ai_settings()
        self.api_key = api_key or cfg.OPENROUTER_API_KEY
        self.model_name = model_name or cfg.OPENROUTER_MODEL
        self.timeout_seconds = timeout_seconds or cfg.OPENROUTER_TIMEOUT_SECONDS

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        if not self.api_key:
            raise AIConfigurationError("OpenRouter API key is not configured")

        start = time.monotonic()
        try:
            client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self.api_key,
                timeout=self.timeout_seconds,
            )

            kwargs = {}
            if response_mime_type == "application/json":
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                **kwargs,
            )

            text = response.choices[0].message.content if response.choices else None
            if not text:
                raise AIResponseParsingError("OpenRouter SDK returned empty response text")

            logger.warning(
                "\n========== OPENROUTER RAW LLM RESPONSE START ==========\n"
                "Model: %s\n"
                "Raw Text:\n%s\n"
                "========== OPENROUTER RAW LLM RESPONSE END ==========",
                self.model_name,
                text.strip(),
            )

            return text.strip()

        except APIStatusError as e:
            if e.status_code == 429:
                raise AIRateLimitError(f"OpenRouter rate limit exceeded: {e}") from e
            if e.status_code in (400, 401, 403):
                raise AIConfigurationError(f"OpenRouter auth/client error ({e.status_code}): {e}") from e
            raise AIServiceUnavailableError(f"OpenRouter server error ({e.status_code}): {e}") from e
        except APITimeoutError as e:
            raise AIServiceUnavailableError(f"OpenRouter request timed out: {e}") from e
        except APIConnectionError as e:
            raise AIServiceUnavailableError(f"OpenRouter connection error: {e}") from e
        except APIError as e:
            raise AIException(f"OpenRouter API error: {e}") from e
        except Exception as e:
            if isinstance(e, AIException):
                raise
            raise AIException(f"OpenRouter SDK execution failed: {e}") from e

    async def generate_async(
        self,
        system_prompt: str,
        user_prompt: str,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        if not self.api_key:
            raise AIConfigurationError("OpenRouter API key is not configured")

        start = time.monotonic()
        try:
            client = AsyncOpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self.api_key,
                timeout=self.timeout_seconds,
            )

            kwargs = {}
            if response_mime_type == "application/json":
                kwargs["response_format"] = {"type": "json_object"}

            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                **kwargs,
            )

            text = response.choices[0].message.content if response.choices else None
            if not text:
                raise AIResponseParsingError("OpenRouter SDK returned empty response text")

            logger.warning(
                "\n========== OPENROUTER RAW LLM RESPONSE START ==========\n"
                "Model: %s\n"
                "Raw Text:\n%s\n"
                "========== OPENROUTER RAW LLM RESPONSE END ==========",
                self.model_name,
                text.strip(),
            )

            return text.strip()

        except APIStatusError as e:
            if e.status_code == 429:
                raise AIRateLimitError(f"OpenRouter rate limit exceeded: {e}") from e
            if e.status_code in (400, 401, 403):
                raise AIConfigurationError(f"OpenRouter auth/client error ({e.status_code}): {e}") from e
            raise AIServiceUnavailableError(f"OpenRouter server error ({e.status_code}): {e}") from e
        except APITimeoutError as e:
            raise AIServiceUnavailableError(f"OpenRouter request timed out: {e}") from e
        except APIConnectionError as e:
            raise AIServiceUnavailableError(f"OpenRouter connection error: {e}") from e
        except APIError as e:
            raise AIException(f"OpenRouter API error: {e}") from e
        except Exception as e:
            if isinstance(e, AIException):
                raise
            raise AIException(f"OpenRouter SDK execution failed: {e}") from e
