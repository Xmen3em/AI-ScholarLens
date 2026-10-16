"""Optional local stdio MCP; no network transport, arbitrary paths or owner arguments."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from src.services.study.store import StudyStore
from src.services.study.tools import StudyTools


def create_study_mcp(store: StudyStore) -> FastMCP:
    server = FastMCP("ScholarLens private paper study")
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=annotations)
    def paper_overview() -> dict:
        """Read the configured owner's current paper identity, version and evidence directory."""
        return StudyTools(store, max_calls=1).overview()

    @server.tool(annotations=annotations)
    def search_evidence(query: str, limit: int = 6) -> list[dict]:
        """Search only the current paper's original source evidence; use English keywords."""
        return StudyTools(store, max_calls=1).search(query, limit)

    @server.tool(annotations=annotations)
    def read_evidence(ids: list[str]) -> list[dict]:
        """Read up to eight validated evidence IDs from the current paper."""
        return StudyTools(store, max_calls=1).read(ids)

    @server.tool(annotations=annotations)
    def study_notes() -> dict:
        """Read the current generated lesson, explicitly labeled as not primary evidence."""
        return StudyTools(store, max_calls=1).notes()

    return server
