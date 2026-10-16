from typing import Annotated, List, Union
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from src.services.hf.registry import REGISTERED_HF_MODELS


class DefaultSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__"
    )

class ArxivSettings(DefaultSettings):
    """arXiv API client settings."""

    base_url: str = "https://export.arxiv.org/api/query"
    namespaces: dict = Field(
        default={
            "atom": "http://www.w3.org/2005/Atom",
            "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
    )
    pdf_cache_dir: str = "./data/arxiv_pdfs"
    rate_limit_delay: float = 3.0  # seconds between requests
    timeout_seconds: int = 30
    # Total papers per run across every allowlisted AI category. The categories
    # themselves are fixed in src/policies/ai_scope.py and are not configurable.
    max_results: int = 10


class PDFParserSettings(DefaultSettings):
    """PDF parser service settings."""

    # 45, not 30: a sample of the live corpus skipped 5 of 6 papers on page count
    # alone, at 31-41 pages. Papers skipped here never get raw_text, so they are
    # invisible to retrieval.
    max_pages: int = 45
    max_file_size_mb: int = 20
    do_ocr: bool = False
    # The parser stores sections and raw text only (docling.py returns tables=[]), so table
    # structure detection would load a second model and run inference for discarded output.
    do_table_structure: bool = False
    
class Settings(DefaultSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)
    
    app_version: str = "0.1.0"
    debug: bool = True
    environment: str = "development"
    service_name: str = "AI-ScholarLens"
    api_key: SecretStr | None = Field(default=None, min_length=32)
    api_requests_per_minute: int = Field(default=60, ge=1)
    api_generations_per_minute: int = Field(default=6, ge=1)
    api_rate_limit_path: str = "./data/rate_limits.sqlite3"
    local_tracing_enabled: bool = False
    local_tracing_url: str = "http://127.0.0.1:3000"
    local_tracing_public_key: SecretStr | None = None
    local_tracing_secret_key: SecretStr | None = None
    monitoring_directory: str | None = None
    answer_cache_enabled: bool = False
    answer_cache_url: SecretStr = SecretStr("redis://127.0.0.1:6380/0")
    answer_cache_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    agent_enabled: bool = False
    agent_deadline_seconds: int = Field(default=90, ge=1, le=120)
    agent_node_timeout_seconds: int = Field(default=30, ge=1, le=60)
    hf_inference_enabled: bool = False
    hf_token: SecretStr | None = None
    hf_models: Annotated[list[str], NoDecode] = Field(default=["openai/gpt-oss-120b:groq"], min_length=1, max_length=2)
    hf_default_model: str = "openai/gpt-oss-120b:groq"
    hf_timeout_seconds: float = Field(default=30, ge=1, le=30)

    @field_validator("hf_models", mode="before")
    @classmethod
    def parse_hf_models(cls, value):
        if isinstance(value, str):
            return [model.strip() for model in value.split(",") if model.strip()]
        return value

    @model_validator(mode="after")
    def hosted_configuration(self):
        if (len(set(self.hf_models)) != len(self.hf_models)
                or not set(self.hf_models) <= REGISTERED_HF_MODELS
                or self.hf_default_model not in self.hf_models):
            raise ValueError("HF requires explicit registered model/provider pairs and an allowed default")
        if self.hf_inference_enabled:
            token = self.hf_token.get_secret_value() if self.hf_token else ""
            if (not token.startswith("hf_") or len(token) < 16 or len(token) > 512
                    or not token[3:].isascii() or not token[3:].isalnum()):
                raise ValueError("HF inference requires a valid server-side HF token")
            if self.api_key is None:
                raise ValueError("HF inference requires the existing API key protection")
            if self.answer_cache_enabled:
                raise ValueError("HF inference requires an uncached profile")
        return self

    @model_validator(mode="after")
    def local_trace_destination(self):
        if self.local_tracing_enabled:
            url = urlsplit(self.local_tracing_url)
            if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1", "langfuse-web", "host.docker.internal"}
                    or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
                raise ValueError("Tracing requires a local HTTP origin")
            if not self.local_tracing_public_key or not self.local_tracing_secret_key:
                raise ValueError("Local tracing requires project credentials")
        if self.answer_cache_enabled:
            url = urlsplit(self.answer_cache_url.get_secret_value())
            if url.scheme != "redis" or url.hostname not in {"localhost", "127.0.0.1", "::1", "redis-cache"} or url.query:
                raise ValueError("Answer caching requires local Redis")
            if self.api_key is None:
                raise ValueError("Answer caching requires the configured API key for signing")
            for origin, allowed in [(self.opensearch_host, "opensearch"), (self.ollama_host, "ollama")]:
                if urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1", allowed}:
                    raise ValueError("Cache revision probes must remain local")
        return self

    @field_validator("api_key", "hf_token", mode="before")
    @classmethod
    def empty_key(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def require_access_key(self):
        if self.environment not in {"development", "test"} and self.api_key is None:
            raise ValueError("API_KEY is required outside development/test")
        return self
    
    postgres_database_url: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0
    
    opensearch_host: str = "http://localhost:9200"
    
    ollama_host: str = "http://localhost:11434"
    # NoDecode: without it pydantic-settings JSON-decodes a complex field straight from
    # .env and raises before parse_ollama_models ever sees the comma-separated string.
    ollama_models: Annotated[List[str], NoDecode] = Field(default=["llama3.2:1b"])
    ollama_default_model: str = "llama3.2:1b"
    # Pull with `docker compose exec ollama ollama pull nomic-embed-text`. Changing this
    # to a model of a different width means rebuilding the chunk index, because the
    # knn_vector mapping fixes the dimension.
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_timeout: int = 300
    # Expansion improves evidence coverage but regressed relevance in the holdout.
    # Keep conservative production behavior until selector quality is justified.
    rag_sentence_candidates_per_passage: int = Field(default=1, ge=1, le=3)
    # Opt-in total cap; frozen evaluation profiles must explicitly admit it.
    rag_max_sentence_candidates: int | None = Field(default=None, ge=1, le=10)

    @field_validator("rag_max_sentence_candidates", mode="before")
    @classmethod
    def empty_catalog_limit(cls, value):
        return None if value == "" else value
    
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings)

    @field_validator("ollama_models", mode="before")
    @classmethod
    def parse_ollama_models(cls, v):
        if isinstance(v, str):
            return [model.strip() for model in v.split(",") if model.strip()]
        return v
    
def get_settings() -> Settings:
    return Settings()
