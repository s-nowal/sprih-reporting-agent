"""Application settings loaded from environment variables (prefix: SPRIH_)."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load ALL .env vars into os.environ (ANTHROPIC_API_KEY, LANGSMITH_*, SPRIH_*, etc.)
# so every library (langchain, anthropic SDK, etc.) can read its own vars.
# Anchored to the repo root so the correct .env is loaded regardless of CWD.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)


class Settings(BaseSettings):
    # Reads only SPRIH_* vars from os.environ (not from .env directly)
    model_config = SettingsConfigDict(env_prefix="SPRIH_")

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    auth_dev_mode: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]
    debug: bool = True

    # Database (MariaDB)
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "esg"
    db_user: str = "root"
    db_password: str = "dev"

    # Storage (local filesystem simulating S3)
    storage_root: str = "./data/s3"


settings = Settings()
