"""
Configuration settings for AI infrastructure.
"""

from typing import Optional
from pydantic_settings import BaseSettings


class AISettings(BaseSettings):
    """Configuration options for AI providers loaded from environment variables."""

    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_SECONDS: float = 10.0
    DEFAULT_PROVIDER: str = "gemini"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def effective_gemini_api_key(self) -> Optional[str]:
        """Returns GEMINI_API_KEY or falls back to GOOGLE_API_KEY."""
        return self.GEMINI_API_KEY or self.GOOGLE_API_KEY


def get_ai_settings() -> AISettings:
    """Factory function returning an instance of AISettings."""
    return AISettings()
