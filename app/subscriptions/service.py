# from datetime import datetime, timezone

# from google.oauth2 import service_account
# from googleapiclient.discovery import build

# from sqlalchemy.orm import Session

# from app.users.models import User, SubscriptionEnum


# SERVICE_ACCOUNT_FILE = "paper-trade-496205-3573c4335a37.json"

# PACKAGE_NAME = "com.sourav.papertrade"


# def get_android_publisher():
#     credentials = service_account.Credentials.from_service_account_file(
#         SERVICE_ACCOUNT_FILE,
#         scopes=[
#             "https://www.googleapis.com/auth/androidpublisher"
#         ],
#     )

#     return build(
#         "androidpublisher",
#         "v3",
#         credentials=credentials,
#         cache_discovery=False,
#     )


# def verify_subscription_purchase(
#     db: Session,
#     user: User,
#     product_id: str,
#     purchase_token: str,
# ):
#     service = get_android_publisher()

#     request = service.purchases().subscriptions().get(
#         packageName=PACKAGE_NAME,
#         subscriptionId=product_id,
#         token=purchase_token,
#     )

#     response = request.execute()

#     expiry_time_millis = response.get("expiryTimeMillis")

#     auto_renewing = response.get("autoRenewing", False)

#     payment_state = response.get("paymentState")

#     # paymentState == 1 means payment received successfully
#     if payment_state != 1:
#         return {
#             "success": False,
#             "message": "Payment not completed"
#         }

#     expiry_datetime = datetime.fromtimestamp(
#         int(expiry_time_millis) / 1000,
#         tz=timezone.utc,
#     )

#     # UPDATE USER
#     user.subscription = SubscriptionEnum.PRO # type: ignore

#     user.subscription_product_id = product_id # type: ignore

#     user.purchase_token = purchase_token # type: ignore

#     user.subscription_platform = "android" # type: ignore

#     user.subscription_expiry = expiry_datetime # type: ignore

#     user.auto_renewing = auto_renewing

#     db.commit()

#     db.refresh(user)

#     return {
#         "success": True,
#         "message": "Subscription verified",
#         "expiry": expiry_datetime,
#     }


import logging
import os
from datetime import datetime, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session
from app.users.models import User, SubscriptionEnum
from functools import lru_cache

@lru_cache(maxsize=1)
def get_android_publisher():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/androidpublisher"],
    )
    return build(
        "androidpublisher",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

logger = logging.getLogger(__name__)

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "paper-trade-496205-3573c4335a37.json")
PACKAGE_NAME = os.getenv("GOOGLE_PLAY_PACKAGE_NAME", "com.sourav.papertrade")
ALLOWED_PRODUCT_IDS = {
    pid.strip()
    for pid in os.getenv("GOOGLE_PLAY_PRODUCT_IDS", "papertrade.pro.monthly").split(",")
    if pid.strip()
}

# Google paymentState: 1 = payment received, 2 = free trial
ACCEPTED_PAYMENT_STATES = {1, 2}


def verify_subscription_purchase(
    db: Session,
    user: User,
    product_id: str,
    purchase_token: str,
):
    if product_id not in ALLOWED_PRODUCT_IDS:
        return {"success": False, "message": "Invalid product ID"}

    linked_to_other = (
        db.query(User)
        .filter(User.purchase_token == purchase_token, User.id != user.id)
        .first()
    )
    if linked_to_other:
        logger.warning("Purchase token already linked to another account")
        return {"success": False, "message": "This purchase is already linked to another account"}

    try:
        service = get_android_publisher()
        response = (
            service.purchases()
            .subscriptions()
            .get(packageName=PACKAGE_NAME, subscriptionId=product_id, token=purchase_token)
            .execute()
        )
    except HttpError as e:
        logger.warning("Google Play verification failed with status %s", getattr(e.resp, "status", None))
        return {"success": False, "message": "Could not verify purchase with Google Play"}
    except Exception:
        logger.exception("Unexpected error during Google Play verification")
        return {"success": False, "message": "Verification failed, please try again"}

    if response.get("paymentState") not in ACCEPTED_PAYMENT_STATES:
        return {"success": False, "message": "Payment not completed"}

    expiry_time_millis = response.get("expiryTimeMillis")
    if not expiry_time_millis:
        return {"success": False, "message": "Invalid subscription data"}

    expiry_datetime = datetime.fromtimestamp(int(expiry_time_millis) / 1000, tz=timezone.utc)
    if expiry_datetime <= datetime.now(timezone.utc):
        return {"success": False, "message": "Subscription has expired"}

    if response.get("acknowledgementState") == 0:
        try:
            service.purchases().subscriptions().acknowledge(
                packageName=PACKAGE_NAME,
                subscriptionId=product_id,
                token=purchase_token,
                body={},
            ).execute()
        except HttpError:
            logger.warning("Failed to acknowledge purchase")

    user.subscription = SubscriptionEnum.PRO  # type: ignore
    user.subscription_product_id = product_id  # type: ignore
    user.purchase_token = purchase_token  # type: ignore
    user.subscription_platform = "android"  # type: ignore
    user.subscription_expiry = expiry_datetime  # type: ignore
    user.auto_renewing = response.get("autoRenewing", False)

    db.commit()
    db.refresh(user)

    logger.info("Subscription verified for user %s", user.id)

    return {"success": True, "message": "Subscription verified", "expiry": expiry_datetime}