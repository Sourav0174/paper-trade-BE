from pydantic import BaseModel


class VerifySubscriptionRequest(BaseModel):
    product_id: str
    purchase_token: str
    purchase_id: str | None = None