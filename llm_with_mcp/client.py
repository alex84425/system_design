"""
Usage:
  uv run python client.py '<json_string>'

The JSON must match:
  {
    "plan_name": str,
    "description": str,
    "test_cases": [{"title": str, "steps": [str], "expected_result": str}]
  }
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(payload: dict):
    params = StdioServerParameters(
        command="uv",
        args=["run", "python", "server.py"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("create_plan", payload)
            raw = result.content[0].text
            try:
                print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
            except Exception:
                print(raw)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python client.py '<json>'")
        sys.exit(1)
    asyncio.run(main(json.loads(sys.argv[1])))
