from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_DEFAULT_DB = _APP_DIR / "test.db"

# Creates Settings class which inherits from pydantics BaseSettings
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[str(_APP_DIR / ".env"), str(_APP_DIR.parent.parent / ".env")],
        case_sensitive=False,
    )

    # Required settings :str must be string and gets value from .env using pydantic
    database_url: str = f"sqlite:///{_DEFAULT_DB}"
    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash-lite"
    google_oauth_client_id: Optional[str] = None
    google_oauth_client_secret: Optional[str] = None
    google_oauth_redirect_uri: Optional[str] = None
    fernet_key: Optional[str] = None
    firebase_project_id: Optional[str] = None
    firebase_service_account_path: Optional[str] = None
    firebase_service_account_json: Optional[str] = None
    firebase_firestore_tokens_collection: str = "google_credentials"
    firebase_web_api_key: Optional[str] = None
    firebase_web_auth_domain: Optional[str] = None
    firebase_web_app_id: Optional[str] = None
    firebase_web_measurement_id: Optional[str] = None

    # gets mode and log should be string in env if not defaults to dev and info
    app_env: str = "development"
    log_level: str = "info"

settings = Settings()

# Defensive: if the DB URL was set as "database_url=sqlite:////path", strip the prefix.
if settings.database_url.startswith("database_url="):
    settings.database_url = settings.database_url.split("=", 1)[1]
