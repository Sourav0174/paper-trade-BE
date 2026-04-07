from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Twelve Data
    TWELVE_DATA_API_KEY: str

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings() # type: ignore