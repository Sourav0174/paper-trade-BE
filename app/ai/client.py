"""
Unified AI Client interface for application consumption.
"""

from typing import Optional
from app.ai.providers.base import BaseAIProvider
from app.ai.providers.openrouter import OpenRouterProvider
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
            self.provider = OpenRouterProvider(settings=cfg)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        """Delegates synchronous generation request to the underlying provider."""
        return self.provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_mime_type=response_mime_type,
        )

    async def generate_async(
        self,
        system_prompt: str,
        user_prompt: str,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        """Delegates asynchronous generation request to the underlying provider."""
        return await self.provider.generate_async(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_mime_type=response_mime_type,
        )
