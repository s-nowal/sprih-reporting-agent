"""Application settings loaded from environment variables (prefix: SPRIH_)."""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load ALL .env vars into os.environ (ANTHROPIC_API_KEY, LANGSMITH_*, SPRIH_*, etc.)
# so every library (langchain, anthropic SDK, etc.) can read its own vars.
load_dotenv()


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
    storage_backend: str = "local"  # "local" | "s3" — add branches in storage.get_storage()

    # --- Default enterprise (dev) --------------------------------------------
    # The auth dev-mode bypass uses this when no x-enterprise-id header is sent.
    # Also used as the seed enterprise row at startup so foreign-key references
    # (jobs, threads, mirror_credentials) resolve in a fresh database.
    default_enterprise_id: str = "sprih"
    default_enterprise_name: str = "Sprih"

    # --- Google Drive integration --------------------------------------------
    # OAuth client credentials for the "Sprih agent" GCP project. The agent
    # signs in once as the workspace user (e.g. sachchit.vekaria@sprih.com)
    # and the resulting refresh token is stored per enterprise.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Per-agent mirror policy: which workspace subdirectories sync to Drive.
    # Keys are graph names (assistant_id), values are subdir names. Anything
    # not listed (e.g. "workspace/", "reference/") stays in S3 only.
    drive_mirror_subdirs: dict[str, list[str]] = {
        "reporting-agent": ["input", "output"],
    }


settings = Settings()
