"""
Real end-to-end test: spawns metis_mcp.server as a subprocess over stdio and
calls actual tools through the MCP client protocol -- this proves the server
works as an MCP server, not just that the Python module imports cleanly.
"""
import asyncio
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_DIR = Path(__file__).resolve().parent


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "metis_mcp.server"],
        cwd=str(SERVER_DIR),
        # The MCP SDK's default only forwards an allowlisted subset of env
        # vars to the subprocess, not the full parent environment -- real
        # gap found running this against graph.backend=neo4j, which needs
        # METIS_NEO4J_PASSWORD (config_manager.py's password_env indirection)
        # to reach the spawned server process. Inherit everything here since
        # this is a local dev/test harness, not the production deployment
        # path (which uses Streamable HTTP, not stdio spawn, per Phase 6).
        env=os.environ.copy(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"Server exposes {len(tools.tools)} tools:")
            for t in tools.tools:
                print(f"  - {t.name}")
            assert len(tools.tools) == 12, f"expected 12 tools, got {len(tools.tools)}"

            print("\n--- metis_get_context('CONST-047') ---")
            r = await session.call_tool("metis_get_context", {"anchor": "CONST-047"})
            print(r.content[0].text[:500])

            print("\n--- metis_get_traceability('CONST-047') ---")
            r = await session.call_tool("metis_get_traceability", {"node_id": "CONST-047"})
            print(r.content[0].text[:500])

            print("\n--- metis_check_coverage('CONST-047') ---")
            r = await session.call_tool("metis_check_coverage", {"target_id": "CONST-047"})
            print(r.content[0].text[:500])

            print("\n--- metis_quality_score(scope='ConstitutionRule') ---")
            r = await session.call_tool("metis_quality_score", {"scope": "ConstitutionRule"})
            print(r.content[0].text[:500])

            print("\n--- metis_get_context('CONST-99999') [should be a clean not-found] ---")
            r = await session.call_tool("metis_get_context", {"anchor": "CONST-99999"})
            print(r.content[0].text[:300])

            print("\n--- metis_submit_episode(...) [should be refused per REQ-METIS-CPT-01] ---")
            r = await session.call_tool("metis_submit_episode", {
                "episode_type": "test", "payload": {}, "source_ref": "test"
            })
            print(r.content[0].text[:300])

            print("\nAll calls completed without error.")

asyncio.run(main())
