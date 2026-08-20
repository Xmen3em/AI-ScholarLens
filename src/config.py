from typing import List, Union
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class DefaultSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__"
    )

class Settings(DefaultSettings):
    
    app_version: str = "0.1.0"
    debug: bool = True
    environment: str = "development"
    service_name: str = "AI-ScholarLens"
    
    postgres_database_url: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0
    
    opensearch_host: str = "http://localhost:9200"
    
    ollama_host: str = "http://localhost:11434"
    ollama_models: Union[str, List[str]] = Field(default=["gpt-oss:20b", "llama3.2:1b"])
    ollama_default_model: str = "llama3.2:1b"
    ollama_timeout: int = 300
    
    @field_validator("ollama_models", mode="before")
    @classmethod
    def parse_ollama_models(cls, v):
        if isinstance(v, str):
            return [model.strip() for model in v.split(",") if model.strip()]
        return v
    
def get_settings() -> Settings:
    return Settings()