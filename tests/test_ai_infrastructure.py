"""
Unit tests for AI Infrastructure Layer (OpenRouterProvider & AIClient).

Tests:
- Async generation with OpenRouterProvider
- Error mapping for rate limits, status codes, timeouts, and empty responses
- Facade delegation via AIClient
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from openai import APIStatusError, APITimeoutError
from app.ai.client import AIClient
from app.ai.exceptions import (
    AIConfigurationError,
    AIRateLimitError,
    AIResponseParsingError,
    AIServiceUnavailableError,
)
from app.ai.providers.openrouter import OpenRouterProvider


class TestAIInfrastructure(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.provider = OpenRouterProvider(api_key="test-key", model_name="deepseek/deepseek-chat-v3")

    @patch("app.ai.providers.openrouter.AsyncOpenAI")
    async def test_successful_generate_async(self, mock_async_openai):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"headline": "Great job"}'

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        res = await self.provider.generate_async("System prompt", "User prompt")
        self.assertEqual(res, '{"headline": "Great job"}')

    @patch("app.ai.providers.openrouter.AsyncOpenAI")
    async def test_empty_response_raises_parsing_error(self, mock_async_openai):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        with self.assertRaises(AIResponseParsingError):
            await self.provider.generate_async("System prompt", "User prompt")

    @patch("app.ai.providers.openrouter.AsyncOpenAI")
    async def test_timeout_raises_service_unavailable(self, mock_async_openai):
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock(
            side_effect=APITimeoutError(request=MagicMock())
        )
        mock_async_openai.return_value = mock_client_instance

        with self.assertRaises(AIServiceUnavailableError):
            await self.provider.generate_async("System prompt", "User prompt")

    @patch("app.ai.providers.openrouter.AsyncOpenAI")
    async def test_rate_limit_raises_rate_limit_error(self, mock_async_openai):
        mock_response = MagicMock()
        mock_response.status_code = 429

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock(
            side_effect=APIStatusError(message="Rate limit exceeded", response=mock_response, body=None)
        )
        mock_async_openai.return_value = mock_client_instance

        with self.assertRaises(AIRateLimitError):
            await self.provider.generate_async("System prompt", "User prompt")

    async def test_ai_client_delegates_to_provider(self):
        mock_provider = MagicMock()
        mock_provider.generate_async = AsyncMock(return_value="OK")

        client = AIClient(provider=mock_provider)
        res = await client.generate_async("System", "User")
        self.assertEqual(res, "OK")
        mock_provider.generate_async.assert_called_once_with(
            system_prompt="System",
            user_prompt="User",
            response_mime_type="application/json",
        )


if __name__ == "__main__":
    unittest.main()
