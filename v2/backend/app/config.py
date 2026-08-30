from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
_ROOT = ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[str(_ROOT / ".env"), str(_ROOT / "v2" / ".env")],
        case_sensitive=False,
        extra="ignore",
    )

    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-flash-lite"

    google_oauth_client_id: Optional[str] = None
    google_oauth_client_secret: Optional[str] = None
    google_oauth_redirect_uri: Optional[str] = None

    firebase_project_id: Optional[str] = None
    firebase_service_account_path: Optional[str] = None
    firebase_service_account_json: Optional[str] = None
    firebase_transactions_collection: str = "transactions"
    firebase_demo_collection: str = "receipts_v2_demo"

    fernet_key: Optional[str] = None
    frontend_url: str = "http://localhost:3000"
    cors_allow_origins: Optional[str] = None

    llm_batch_window_ms: int = 120
    llm_batch_max_size: int = 12
    llm_rpm_limit: int = 9
    llm_min_interval_seconds: float = 6.0
    llm_max_retries: int = 2
    llm_request_timeout: float = 180.0

    # "memory" keeps paused reviews in-process; "sqlite" keeps them across
    # restarts and needs `pip install langgraph-checkpoint-sqlite`.
    checkpoint_backend: str = "memory"
    checkpoint_path: Optional[str] = None

    app_env: str = "development"

    @property
    def data_dir(self) -> Path:
        return ROOT / "v2" / "backend" / "data"

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_url.rstrip("/")} if self.frontend_url else set()
        for extra in (self.cors_allow_origins or "").split(","):
            if extra.strip():
                origins.add(extra.strip().rstrip("/"))
        return sorted(origins)


settings = Settings()
settings.gemini_model = (settings.gemini_model or "").strip()
