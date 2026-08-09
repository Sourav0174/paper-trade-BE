"""
Configuration settings for AI infrastructure.
"""

from typing import Optional
from pydantic_settings import BaseSettings


class AISettings(BaseSettings):
    """Configuration options for AI providers loaded from environment variables."""

    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "deepseek/deepseek-chat-v3"
    OPENROUTER_TIMEOUT_SECONDS: float = 10.0

    AI_PROVIDER: str = "openrouter"

    class Config:
        env_file = ".env"
        extra = "ignore"


def get_ai_settings() -> AISettings:
    """Factory function returning an instance of AISettings."""
    return AISettings()
