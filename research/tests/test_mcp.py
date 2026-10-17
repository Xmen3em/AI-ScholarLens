import asyncio
import tempfile
import unittest
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session
from src.services.study.mcp_server import create_study_mcp
from src.services.study.store import StudyStore


class MCPTests(unittest.TestCase):
    def test_real_sdk_lists_only_read_operations_without_caller_owner_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            server = create_study_mcp(StudyStore(Path(folder) / "store.sqlite3", "owner"))
            listed = asyncio.run(server.list_tools())
            assert {tool.name for tool in listed} == {"paper_overview", "search_evidence", "read_evidence", "study_notes"}
            for tool in listed:
                assert tool.annotations.readOnlyHint and not tool.annotations.openWorldHint
                assert "owner" not in tool.inputSchema.get("properties", {})
                assert "path" not in tool.inputSchema.get("properties", {})

    def test_protocol_initialization_and_tool_failure_do_not_expose_other_owners(self):
        async def check(path):
            server = create_study_mcp(StudyStore(path, "owner-with-no-paper"))
            async with create_connected_server_and_client_session(server, raise_exceptions=True) as client:
                await client.initialize()
                assert len((await client.list_tools()).tools) == 4
                result = await client.call_tool("paper_overview", {})
                assert result.isError
                assert "active_paper_required" in result.content[0].text
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(check(Path(folder) / "store.sqlite3"))


if __name__ == "__main__":
    unittest.main()
