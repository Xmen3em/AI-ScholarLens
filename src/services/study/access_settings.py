"""Multi-user beta settings (docs/specs/multi-user.md §8); out-of-range values refuse startup."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from src.config import DefaultSettings


class AccessSettings(DefaultSettings):
    model_config = SettingsConfigDict(env_prefix="STUDY_", env_file=".env", extra="ignore", frozen=True)

    multi_user: bool = False
    daily_papers: int = Field(default=3, ge=1, le=50)
    daily_questions: int = Field(default=30, ge=1, le=500)
    daily_usd_ceiling: float = Field(default=2.00, ge=0.10, le=100)
    parallel_jobs: int = Field(default=3, ge=1, le=4)
    messages_per_minute: int = Field(default=6, ge=1, le=60)
    retention_days: int = Field(default=30, ge=1, le=365)
