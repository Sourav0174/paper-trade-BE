"""
AI Infrastructure Exception Hierarchy.
"""


class AIException(Exception):
    """Base exception for all AI infrastructure errors."""

    pass


class AIConfigurationError(AIException):
    """Raised when required AI provider settings or API keys are missing or invalid."""

    pass


class AIServiceUnavailableError(AIException):
    """Raised when an AI provider endpoint is unreachable or returns a 5xx status code."""

    pass


class AIResponseParsingError(AIException):
    """Raised when an AI provider returns an empty, unparseable, or malformed response."""

    pass


class AIRateLimitError(AIException):
    """Raised when an AI provider returns a rate limit (429) error."""

    pass
