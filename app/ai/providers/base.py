"""
Abstract base class interface for AI infrastructure providers.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseAIProvider(ABC):
    """Abstract interface exposing a standard generation method across AI providers."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        """
        Executes generation request and returns raw string response.

        Raises:
            AIException subclasses on failure.
        """
        pass
