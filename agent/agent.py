"""Sage Agent entrypoint for AgentCore Runtime.

Uses the BedrockAgentCoreApp SDK to expose the agent via the standard
AgentCore contract (/invocations POST + /ping GET). The SDK handles
HTTP serving, streaming, and health checks automatically.

For each request the agent creates a short-lived MCPClient that connects
to the AgentCore Gateway via Streamable HTTP, forwarding the tenant
header so data tools can scope their responses to the correct tenant.

Skills are loaded from the AgentCore Registry at startup. The agent
fetches all approved AGENT_SKILLS records, creates Skill instances via
``Skill.from_content()``, and passes them to the Strands ``AgentSkills``
plugin. The plugin injects lightweight skill descriptors into the system
prompt and provides a built-in ``skills`` tool for on-demand loading.

Architecture:
  Frontend → Agent (AgentCore) → Gateway (AgentCore) → MCP Server (AgentCore)
  Skills are fetched from AgentCore Registry at startup (IAM auth).

Auth:
  Agent → Gateway: OAuth M2M token fetched from Cognito using the same
    unified pool as the frontend/MCP server. Credentials come from:
      GATEWAY_URL                — AgentCore Gateway MCP endpoint URL
      GATEWAY_AUTH_TOKEN_ENDPOINT — Cognito token endpoint
      GATEWAY_AUTH_CLIENT_ID     — Cognito M2M client ID (same pool as MCP)
      GATEWAY_AUTH_CLIENT_SECRET — Cognito M2M client secret
      GATEWAY_AUTH_SCOPE         — OAuth scope (e.g. sage-mcp/tools)

  Agent → Registry: IAM auth (uses the runtime's execution role).
      SKILL_REGISTRY_ID          — AgentCore Registry ID for skill records

Phase 2 JWT tenant extraction:
  When the incoming request carries an ``Authorization: Bearer <token>``
  header, the agent decodes the JWT payload (without signature verification
  — the AgentCore Runtime already validates the token) and extracts the
  ``custom:tenant_id`` claim. The extracted value is then set as the
  ``X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id`` header for
  downstream gateway propagation.

  Fallback (Phase 1 compatibility): if no JWT is present or the token
  does not contain ``custom:tenant_id``, the agent reads the tenant ID
  directly from the ``X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id``
  request header (the Phase 1 mechanism).

# Local verification (stdio fallback when GATEWAY_URL is not set):
#   export SKILL_REGISTRY_ID=<your-registry-id>
#   uv run python agent/agent.py
"""

import base64
import json
import logging
import os
import time
from pathlib import Path

import boto3
import httpx
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, AgentSkills, Skill
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
TENANT_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id"

GATEWAY_URL = os.environ.get("GATEWAY_URL")
GATEWAY_AUTH_TOKEN_ENDPOINT = os.environ.get("GATEWAY_AUTH_TOKEN_ENDPOINT")
GATEWAY_AUTH_CLIENT_ID = os.environ.get("GATEWAY_AUTH_CLIENT_ID")
GATEWAY_AUTH_CLIENT_SECRET = os.environ.get("GATEWAY_AUTH_CLIENT_SECRET")
GATEWAY_AUTH_SCOPE = os.environ.get("GATEWAY_AUTH_SCOPE")
SKILL_REGISTRY_ID = os.environ.get("SKILL_REGISTRY_ID")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# Simple in-process token cache: (token, expiry_timestamp)
_token_cache: tuple[str, float] | None = None


def _load_base_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",
    region_name="us-east-1",
)


def _fetch_skills_from_registry(registry_id: str) -> list[Skill]:
    """Fetch all approved AGENT_SKILLS records from the AgentCore Registry.

    Connects to the Registry via IAM auth, lists all approved skill
    records, fetches the full SKILL.md content for each, and creates
    ``Skill`` instances via ``Skill.from_content()``.

    Args:
        registry_id: The AgentCore Registry ID to fetch from.

    Returns:
        List of ``Skill`` instances ready for the ``AgentSkills`` plugin.
    """
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # List all approved AGENT_SKILLS records
    records = []
    next_token = None
    while True:
        kwargs: dict = {
            "registryId": registry_id,
            "descriptorType": "AGENT_SKILLS",
            "status": "APPROVED",
        }
        if next_token:
            kwargs["nextToken"] = next_token
        resp = client.list_registry_records(**kwargs)
        records.extend(resp.get("registryRecords", []))
        next_token = resp.get("nextToken")
        if not next_token:
            break

    logger.info("Found %d approved AGENT_SKILLS records in registry %s", len(records), registry_id)

    # Fetch full content for each record and create Skill instances
    skills: list[Skill] = []
    for record in records:
        record_id = record["recordId"]
        record_name = record.get("name", record_id)
        try:
            full = client.get_registry_record(
                registryId=registry_id,
                recordId=record_id,
            )
            descriptors = full.get("descriptors", {})
            agent_skills = descriptors.get("agentSkills", {})
            skill_md = agent_skills.get("skillMd", {})
            content = skill_md.get("inlineContent", "")

            if not content:
                logger.warning("Record %s (%s) has no skillMd content, skipping", record_id, record_name)
                continue

            skill = Skill.from_content(content)
            skills.append(skill)
            logger.info("Loaded skill from registry: %s", skill.name)
        except Exception as e:
            logger.warning("Failed to load skill record %s (%s): %s", record_id, record_name, e)

    return skills


# Initialize the AgentSkills plugin once at module level.
# Skills are fetched from the AgentCore Registry (SKILL_REGISTRY_ID).
if not SKILL_REGISTRY_ID:
    raise RuntimeError(
        "SKILL_REGISTRY_ID environment variable is required. "
        "Run 'uv run python scripts/deploy_registry.py' to create the registry, "
        "then set SKILL_REGISTRY_ID to the registry ID."
    )

_skills = _fetch_skills_from_registry(SKILL_REGISTRY_ID)
logger.info("AgentSkills plugin initialized with %d skills from registry", len(_skills))
_skills_plugin = AgentSkills(skills=_skills)


def _extract_tenant_from_jwt(authorization_header: str | None) -> str | None:
    """Decode a JWT bearer token and extract the ``custom:tenant_id`` claim.

    The AgentCore Runtime validates the JWT signature before the request
    reaches this handler, so no signature verification is needed here.
    We only need to base64-decode the payload segment.

    Args:
        authorization_header: Value of the ``Authorization`` header, e.g.
            ``"Bearer eyJ..."``, or ``None`` if not present.

    Returns:
        The ``custom:tenant_id`` claim value (e.g. ``"axa"``), or ``None``
        if the header is absent, malformed, or the claim is missing.
    """
    if not authorization_header:
        return None

    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    segments = token.split(".")
    if len(segments) != 3:
        return None

    # Decode the payload segment (index 1); add padding as required
    payload_b64 = segments[1]
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        claims = json.loads(payload_bytes)
        return claims.get("custom:tenant_id") or None
    except Exception:
        return None


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
    # Phase 2: extract tenant_id from JWT custom:tenant_id claim
    authorization = request_headers.get("authorization") or request_headers.get(
        "Authorization"
    )
    tenant_id = _extract_tenant_from_jwt(authorization)

    # Phase 1 fallback: read tenant ID directly from the custom header
    if not tenant_id:
        tenant_id = request_headers.get(TENANT_HEADER) or request_headers.get(
            TENANT_HEADER.lower()
        )

    with _make_mcp_client(tenant_id) as mcp_client:
        tools = mcp_client.list_tools_sync()
        agent = Agent(
            model=model,
            system_prompt=_load_base_prompt(),
            plugins=[_skills_plugin],
            tools=tools,
        )
        async for event in agent.stream_async(user_message):
            yield json.loads(json.dumps(event, default=str))


if __name__ == "__main__":
    app.run()
