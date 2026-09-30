"""Application configuration settings using Pydantic v2 Settings."""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the microservice."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "AI Code Review & Automated Test Generator"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # LLM Settings ('auto', 'bedrock', or 'mock')
    LLM_PROVIDER: str = "auto"
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_SESSION_TOKEN: Optional[str] = None
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"

    # Sandbox execution controls
    SANDBOX_TIMEOUT_SECONDS: int = 5
    MAX_CODE_LENGTH: int = 20000

    # API & CORS
    CORS_ORIGINS: List[str] = ["*"]


settings = Settings()
