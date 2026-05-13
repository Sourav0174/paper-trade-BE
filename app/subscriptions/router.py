from fastapi import APIRouter

from app.subscriptions.schema import VerifySubscriptionRequest

router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"]
)


@router.post("/verify")
async def verify_subscription(
    data: VerifySubscriptionRequest,
):
    return {
        "success": True,
        "message": "Subscription route working"
    }