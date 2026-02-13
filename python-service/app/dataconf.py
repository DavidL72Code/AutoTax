# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./receipts.db"
    
    class Config:
        env_file = ".env"

settings = Settings()