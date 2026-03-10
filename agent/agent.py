"""Sage Agent entrypoint for AgentCore Runtime.

Uses the BedrockAgentCoreApp SDK to expose the agent via the standard
AgentCore contract (/invocations POST + /ping GET). The SDK handles
HTTP serving, streaming, and health checks automatically.

For each request the agent creates a short-lived MCPClient that connects
to the AgentCore Gateway via Streamable HTTP, forwarding the tenant
header so data tools can scope their responses to the correct tenant.

Architecture:
  Frontend → Agent (AgentCore) → Gateway (AgentCore) → MCP Server (AgentCore)

Auth:
  Agent → Gateway: OAuth M2M token fetched from Cognito using the same
    unified pool as the frontend/MCP server. Credentials come from:
      GATEWAY_URL                — AgentCore Gateway MCP endpoint URL
      GATEWAY_AUTH_TOKEN_ENDPOINT — Cognito token endpoint
      GATEWAY_AUTH_CLIENT_ID     — Cognito M2M client ID (same pool as MCP)
      GATEWAY_AUTH_CLIENT_SECRET — Cognito M2M client secret
      GATEWAY_AUTH_SCOPE         — OAuth scope (e.g. sage-mcp/tools)

# Local verification (stdio fallback when GATEWAY_URL is not set):
#   uv run python agent/agent.py
"""

import json
import os
import time
from pathlib import Path

import httpx
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

app = BedrockAgentCoreApp()

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
TENANT_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id"

GATEWAY_URL = os.environ.get("GATEWAY_URL")
GATEWAY_AUTH_TOKEN_ENDPOINT = os.environ.get("GATEWAY_AUTH_TOKEN_ENDPOINT")
GATEWAY_AUTH_CLIENT_ID = os.environ.get("GATEWAY_AUTH_CLIENT_ID")
GATEWAY_AUTH_CLIENT_SECRET = os.environ.get("GATEWAY_AUTH_CLIENT_SECRET")
GATEWAY_AUTH_SCOPE = os.environ.get("GATEWAY_AUTH_SCOPE")

# Simple in-process token cache: (token, expiry_timestamp)
_token_cache: tuple[str, float] | None = None


def _load_base_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


model = BedrockModel(
    model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name="us-east-1",
)


def _get_gateway_token() -> str:
    """Fetch (or return cached) M2M token for agent→Gateway auth.

    Uses client_credentials grant against the unified Cognito pool.
    Token is cached until 60s before expiry.

    Returns:
        Bearer token string.
    """
    global _token_cache
    now = time.time()

    if _token_cache and now < _token_cache[1]:
        return _token_cache[0]

    response = httpx.post(
        GATEWAY_AUTH_TOKEN_ENDPOINT,
        data={
            "grant_type": "client_credentials",
            "client_id": GATEWAY_AUTH_CLIENT_ID,
            "client_secret": GATEWAY_AUTH_CLIENT_SECRET,
            "scope": GATEWAY_AUTH_SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    _token_cache = (token, now + expires_in - 60)
    return token


def _make_mcp_client(tenant_id: str | None) -> MCPClient:
    """Create a per-request MCPClient.

    On AWS (GATEWAY_URL set): connects to the AgentCore Gateway via
    Streamable HTTP with Bearer auth + tenant header forwarding.

    Locally (GATEWAY_URL not set): falls back to stdio subprocess.

    Args:
        tenant_id: Tenant ID from the incoming request header, or None.

    Returns:
        A configured MCPClient (use as context manager).
    """
    if GATEWAY_URL:
        token = _get_gateway_token()
        headers = {"Authorization": f"Bearer {token}"}
        if tenant_id:
            headers[TENANT_HEADER] = tenant_id
        return MCPClient(
            lambda: streamablehttp_client(GATEWAY_URL, headers=headers)
        )
    else:
        return MCPClient(
            lambda: stdio_client(
                StdioServerParameters(
                    command="python",
                    args=["-m", "mcp_server.server"],
                )
            )
        )


@app.entrypoint
async def invoke(payload: dict, context: RequestContext):
    """Process a user message and stream response chunks.

    Args:
        payload: Dict with at least a ``prompt`` key.
        context: AgentCore request context — provides ``request_headers``.

    Yields:
        Streamed response events from the Strands agent.
    """
    user_message = payload.get("prompt", "Hello")

    request_headers = context.request_headers or {}
    tenant_id = request_headers.get(TENANT_HEADER) or request_headers.get(
        TENANT_HEADER.lower()
    )

    with _make_mcp_client(tenant_id) as mcp_client:
        tools = mcp_client.list_tools_sync()
        agent = Agent(
            model=model,
            system_prompt=_load_base_prompt(),
            tools=tools,
        )
        async for event in agent.stream_async(user_message):
            yield json.loads(json.dumps(event, default=str))


if __name__ == "__main__":
    app.run()
