from typing import Annotated, List, Union

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
