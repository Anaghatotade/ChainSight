from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    PROJECT_NAME: str = "ChainSight"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql://chainsight_user:chainsight_pass@db:5432/chainsight_db"

    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_super_secret_key_1234567890"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://frontend:3000"]

    ENV: str = "development"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
