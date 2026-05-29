from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # DATABASE
    DATABASE_URL: str

    # JWT / AUTH
    SECRET_KEY: str

    # APP
    APP_BASE_URL: str

    # EMAIL
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASS: str
    FROM_EMAIL: str

    # API
    TWELVE_DATA_API_KEY: str

    # TWILIO
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_VERIFY_SERVICE_SID: str

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()  # type: ignore