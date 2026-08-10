import logging

from fastapi import APIRouter, Depends, HTTPException, status
import pydantic
from sqlalchemy.orm import Session

from app.ai.exceptions import (
    AIConfigurationError,
    AIException,
    AIRateLimitError,
    AIResponseParsingError,
    AIServiceUnavailableError,
)
from app.database import get_db
from app.mentor.schema import DailyMentorReview, MentorResponse, MentorSummary
from app.mentor.service import mentor_service
from app.users.models import User
from app.users.service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mentor", tags=["AI Mentor"])


def _handle_mentor_exception(e: Exception) -> None:
    if isinstance(e, pydantic.ValidationError):
        logger.error("AI Mentor validation error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Mentor coaching service encountered an error. Please try again.",
        )
    if isinstance(e, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, AIRateLimitError):
        logger.warning("AI Mentor rate limited (429): %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Mentor service is temporarily rate limited. Please try again in a moment.",
        )
    if isinstance(e, AIServiceUnavailableError):
        logger.warning("AI Mentor service unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Mentor is temporarily unavailable. Please try again.",
        )
    if isinstance(e, (AIConfigurationError, AIResponseParsingError, AIException)):
        logger.error("AI Mentor service error: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Mentor coaching service encountered an error. Please try again.",
        )
    logger.error("Unexpected error in mentor endpoint: %s: %s", type(e).__name__, e)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An internal server error occurred. Please try again.",
    )


@router.get("/daily-review", response_model=DailyMentorReview, status_code=status.HTTP_200_OK)
async def get_daily_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves or generates the comprehensive daily mentor review for the authenticated user."""
    logger.warning("🔥 MENTOR DAILY REVIEW CALLED user_id=%s", current_user.id)
    try:
        return await mentor_service.generate_daily_review(db, current_user.id) # type: ignore
    except Exception as e:
        _handle_mentor_exception(e)


@router.get("/summary", response_model=MentorSummary, status_code=status.HTTP_200_OK)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves deterministic analytics summary and health metrics for the authenticated user."""
    try:
        return mentor_service.generate_summary(db, current_user.id) # type: ignore
    except Exception as e:
        _handle_mentor_exception(e)


@router.get("/trade-review/{trade_id}", response_model=MentorResponse, status_code=status.HTTP_200_OK)
async def get_trade_review(
    trade_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates focused mentor coaching advice for a specific trade execution."""
    try:
        return await mentor_service.generate_trade_review(db, current_user.id, trade_id) # type: ignore
    except Exception as e:
        _handle_mentor_exception(e)


@router.post("/regenerate", response_model=DailyMentorReview, status_code=status.HTTP_200_OK)
async def regenerate_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forces regeneration of the daily mentor review and AI coaching response."""
    try:
        return await mentor_service.generate_daily_review(db, current_user.id, force_regenerate=True) # type: ignore
    except Exception as e:
        _handle_mentor_exception(e)
