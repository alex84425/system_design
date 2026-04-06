import json

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel


# ── Pydantic Model ──────────────────────────────────────────
class TestCase(BaseModel):
    title: str
    steps: list[str]
    expected_result: str


class CreatePlanRequest(BaseModel):
    plan_name: str
    description: str
    test_cases: list[TestCase]


# ── MCP Server ──────────────────────────────────────────────
mcp = FastMCP("test-plan-server")


@mcp.tool(description=("Create a test plan from natural language. " f"JSON Schema: {CreatePlanRequest.model_json_schema()}"))
def create_plan(
    plan_name: str,
    description: str,
    test_cases: list[dict],
) -> dict:
    """
    Echo back the parsed test plan — no real API call yet.
    Validates that the payload matches CreatePlanRequest schema.
    """
    payload = CreatePlanRequest(
        plan_name=plan_name,
        description=description,
        test_cases=test_cases,
    )
    return json.dumps(
        {
            "status": "ok (echo mode)",
            "received": payload.model_dump(),
        },
        ensure_ascii=False,
    )


if __name__ == "__main__":
    mcp.run()
