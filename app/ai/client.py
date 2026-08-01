"""
Unified AI Client interface for application consumption.
"""

from typing import Optional
from app.ai.providers.base import BaseAIProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.settings import AISettings, get_ai_settings


class AIClient:
    """
    High-level facade client delegating generation tasks to configured AI providers.
    """

    def __init__(
        self,
        provider: Optional[BaseAIProvider] = None,
        settings: Optional[AISettings] = None,
    ):
        cfg = settings or get_ai_settings()
        if provider:
            self.provider = provider
        else:
            if cfg.DEFAULT_PROVIDER == "gemini":
                self.provider = GeminiProvider(settings=cfg)
            else:
                self.provider = GeminiProvider(settings=cfg)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        """Delegates generation request to the underlying provider."""
        return self.provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_mime_type=response_mime_type,
        )
