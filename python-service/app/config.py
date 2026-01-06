from pydantic_settings import BaseSettings
from typing import Optional 

#Creates Settings class which inherits from pydantics BaseSettings
class Settings(BaseSettings): 
    #Required settings :str must be string and gets value from .env using pydantic
    database_url:str 
    anthropic_api_key:str
    openai_api_key:Optional[str]=None #can be string or not app works without it using OpenAi as backup

    # gets mode and log should be string in env if not defaults to dev and info
    app_env:str="development" 
    log-level:str="info"

#pydantic reads setting from .env 
class Config:
    env_file=".env"
    case_sensitive=False
settings=Settings():



