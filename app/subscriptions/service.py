from datetime import datetime, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

from sqlalchemy.orm import Session

from app.users.models import User, SubscriptionEnum


SERVICE_ACCOUNT_FILE = "paper-trade-496205-3573c4335a37.json"

PACKAGE_NAME = "com.sourav.papertrade"


def get_android_publisher():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=[
            "https://www.googleapis.com/auth/androidpublisher"
        ],
    )

    return build(
        "androidpublisher",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def verify_subscription_purchase(
    db: Session,
    user: User,
    product_id: str,
    purchase_token: str,
):
    service = get_android_publisher()

    request = service.purchases().subscriptions().get(
        packageName=PACKAGE_NAME,
        subscriptionId=product_id,
        token=purchase_token,
    )

    response = request.execute()

    expiry_time_millis = response.get("expiryTimeMillis")

    auto_renewing = response.get("autoRenewing", False)

    payment_state = response.get("paymentState")

    # paymentState == 1 means payment received successfully
    if payment_state != 1:
        return {
            "success": False,
            "message": "Payment not completed"
        }

    expiry_datetime = datetime.fromtimestamp(
        int(expiry_time_millis) / 1000,
        tz=timezone.utc,
    )

    # UPDATE USER
    user.subscription = SubscriptionEnum.PRO # type: ignore

    user.subscription_product_id = product_id # type: ignore

    user.purchase_token = purchase_token # type: ignore

    user.subscription_platform = "android" # type: ignore

    user.subscription_expiry = expiry_datetime # type: ignore

    user.auto_renewing = auto_renewing

    db.commit()

    db.refresh(user)

    return {
        "success": True,
        "message": "Subscription verified",
        "expiry": expiry_datetime,
    }