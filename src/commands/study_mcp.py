"""Run explicitly in the optional research environment; default checks configuration only."""

import argparse
import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    telegram_owner_id: int = Field(gt=0, lt=2**52)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    settings = MCPSettings()
    if not args.execute:
        print(json.dumps({"status": "configured_offline", "transport": "stdio", "outbound_calls": 0}))
        return
    from src.services.study.mcp_server import create_study_mcp
    from src.services.study.store import StudyStore

    path = Path("data/study/sessions.sqlite3")
    if not path.is_file() or path.is_symlink():
        raise ValueError("study_store_required")
    server = create_study_mcp(StudyStore(path, str(settings.telegram_owner_id)))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
