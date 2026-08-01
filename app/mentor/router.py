"""
FastAPI Router for AI Mentor endpoints.

Exposes endpoints for daily review, summary metrics, trade-specific review, and review regeneration.
"""

from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.database import get_db
from app.mentor.schema import DailyMentorReview, MentorResponse, MentorSummary
from app.mentor.service import mentor_service
from app.users.models import User
from app.users.service import get_current_user

router = APIRouter(prefix="/mentor", tags=["AI Mentor"])

#Pipeline: Trades → FIFO → Analytics → Rule Engine → Insight Prioritizer → Mentor Service → API Response


@router.get("/daily-review", response_model=DailyMentorReview, status_code=status.HTTP_200_OK)
def get_daily_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves or generates the comprehensive daily mentor review for the authenticated user."""
    try:
        return mentor_service.generate_daily_review(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/summary", response_model=MentorSummary, status_code=status.HTTP_200_OK)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves deterministic analytics summary and health metrics for the authenticated user."""
    try:
        return mentor_service.generate_summary(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/trade-review/{trade_id}", response_model=MentorResponse, status_code=status.HTTP_200_OK)
def get_trade_review(
    trade_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates focused mentor coaching advice for a specific trade execution."""
    try:
        return mentor_service.generate_trade_review(db, current_user.id, trade_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/regenerate", response_model=DailyMentorReview, status_code=status.HTTP_200_OK)
def regenerate_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forces regeneration of the daily mentor review and AI coaching response."""
    try:
        return mentor_service.generate_daily_review(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
