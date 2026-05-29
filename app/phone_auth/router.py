from fastapi import APIRouter, HTTPException
from app.phone_auth.schema import PhoneRequest, VerifyOtpRequest
from app.phone_auth.service import send_otp, verify_otp


router = APIRouter(
    prefix="/phone-auth",
    tags=["Phone Auth"]
)


@router.post("/send-otp")
def send_phone_otp(data: PhoneRequest):
    try:
        status = send_otp(data.phone_number)

        return {
            "success": True,
            "message": "OTP sent successfully",
            "status": status
        }

    except Exception as e:
        print("TWILIO ERROR:", str(e))

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/verify-otp")
def verify_phone_otp(data: VerifyOtpRequest):
    try:
        status = verify_otp(data.phone_number, data.otp)

        if status == "approved":
            return {
                "success": True,
                "message": "Phone number verified"
            }

        return {
            "success": False,
            "message": "Invalid OTP"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))