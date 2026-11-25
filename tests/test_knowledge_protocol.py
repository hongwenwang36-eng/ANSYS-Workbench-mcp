"""Exercise the same Windows stdio transport used by Codex, with an isolated index."""

import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class KnowledgeProtocolTests(unittest.TestCase):
    def test_search_after_fresh_stdio_start(self):
        root = Path(__file__).resolve().parents[1]

        async def check(folder):
            server = StdioServerParameters(
                command=sys.executable,
                args=[str(root / "mcp_server.py")],
                cwd=str(root),
                env={"ANSYS_WORKBENCH_MCP_HOME": folder},
            )
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertIn(
                        "search_examples", {tool.name for tool in tools.tools}
                    )
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "search_examples",
                            {
                                "query": "谐响应",
                                "module": "dynamics",
                                "version": "2025 R1",
                                "limit": 1,
                            },
                        ),
                        timeout=45,
                    )
                    self.assertFalse(result.isError, result.content)
                    hit = result.structuredContent["hits"][0]
                    self.assertEqual(Path(hit["path"]).name, "harmonic.inp")
                    source = await session.call_tool(
                        "get_document", {"document_id": hit["document_id"]}
                    )
                    self.assertIn(
                        "HAR", source.structuredContent["chunks"][0]["text"].upper()
                    )

        with tempfile.TemporaryDirectory() as temp:
            asyncio.run(check(temp))
