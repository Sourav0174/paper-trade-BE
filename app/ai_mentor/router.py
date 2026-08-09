"""
AI Mentor v2 — Step 1: provider connectivity verification.

Temporary debug endpoint proving FastAPI -> AIClient -> OpenRouter -> raw JSON.
No parsing, validation, transformation, caching, or persistence.
Remove once the full pipeline is rebuilt on top of this.
"""

import logging
import time

from fastapi import APIRouter, Depends

from app.ai import AIClient
from app.users.models import User
from app.users.service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-mentor", tags=["AI Mentor v2 (WIP)"])

_SYSTEM_PROMPT = "You are a connectivity check. Respond with a JSON object only."
_USER_PROMPT = 'Return a JSON object with a single key "status" set to "ok".'


@router.get("/debug/ping")
def ai_mentor_ping(current_user: User = Depends(get_current_user)):
    """
    Sends a trivial prompt through AIClient and returns the complete raw SDK response
    object, bypassing text extraction entirely (calls provider.generate_debug()
    instead of provider.generate()). Diagnostic only: OpenRouter is answering, but
    generate()'s content-extraction is raising AIResponseParsingError, so we're
    inspecting the actual response shape before touching that logic.
    """
    client = AIClient()
    model_name = getattr(client.provider, "model_name", "unknown")
    prompt_length = len(_SYSTEM_PROMPT) + len(_USER_PROMPT)

    logger.info("[AI][REQUEST] model=%s prompt_length=%d", model_name, prompt_length)
    start = time.monotonic()

    try:
        response = client.provider.generate_debug( # type: ignore
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_USER_PROMPT,
            response_mime_type="application/json",
        )
        elapsed = time.monotonic() - start
        logger.info(
            "[AI][RESPONSE] model=%s elapsed=%.3fs prompt_length=%d",
            model_name,
            elapsed,
            prompt_length,
        )

        logger.info("[AI][RESPONSE][RAW] type=%s", type(response))
        logger.info("[AI][RESPONSE][RAW] repr=%s", repr(response))
        if hasattr(response, "model_dump"):
            logger.info("[AI][RESPONSE][RAW] model_dump=%s", response.model_dump())
        if hasattr(response, "model_dump_json"):
            logger.info("[AI][RESPONSE][RAW] model_dump_json=%s", response.model_dump_json(indent=2))
        choices = getattr(response, "choices", None)
        logger.info("[AI][RESPONSE][RAW] choices=%s", choices)
        if choices:
            logger.info("[AI][RESPONSE][RAW] choices[0]=%s", choices[0])
            logger.info("[AI][RESPONSE][RAW] choices[0].message=%s", choices[0].message)
            logger.info("[AI][RESPONSE][RAW] choices[0].message.content=%r", choices[0].message.content)

        return response

    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error(
            "[AI][ERROR] model=%s elapsed=%.3fs prompt_length=%d exception_type=%s message=%s",
            model_name,
            elapsed,
            prompt_length,
            type(e).__name__,
            e,
        )
        raise
