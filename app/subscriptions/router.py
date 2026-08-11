from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.database import get_db

from app.subscriptions.schema import (
    VerifySubscriptionRequest,
    RestoreSubscriptionRequest,
)

from app.subscriptions.service import (
    verify_subscription_purchase,
    restore_subscription_purchase,
)

from app.users.models import User

from app.users.service import get_current_user


router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"]
)


@router.post("/verify")
async def verify_subscription(
    data: VerifySubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return verify_subscription_purchase(
        db=db,
        user=current_user,
        product_id=data.product_id,
        purchase_token=data.purchase_token,
    )


@router.post("/restore")
async def restore_subscription(
    data: RestoreSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return restore_subscription_purchase(
        db=db,
        user=current_user,
        product_id=data.product_id,
        purchase_token=data.purchase_token,
    )