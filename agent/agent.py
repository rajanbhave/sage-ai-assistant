"""Sage Agent entrypoint for AgentCore Runtime.

Uses the BedrockAgentCoreApp SDK to expose the agent via the standard
AgentCore contract (/invocations POST + /ping GET). The SDK handles
HTTP serving, streaming, and health checks automatically.

For each request the agent creates a short-lived MCPClient that connects
to the lane-configured AgentCore Gateway target via Streamable HTTP. The
client forwards the exact Runtime-validated user bearer and correlation ID.

Skills are loaded from the AgentCore Registry at startup. The agent
fetches all approved AGENT_SKILLS records, creates Skill instances via
``Skill.from_content()``, and passes them to the Strands ``AgentSkills``
plugin. The plugin injects lightweight skill descriptors into the system
prompt and provides a built-in ``skills`` tool for on-demand loading.

Architecture:
  Frontend → Agent (AgentCore) → Gateway (AgentCore) → MCP Server (AgentCore)
  Skills are fetched from AgentCore Registry at startup (IAM auth).

Auth:
  Agent → Gateway: the original user access-token bearer forwarded from
    the Agent Runtime, with no decoding, re-encoding, exchange, or fallback.
  AgentCore Identity access-token and workload-token decorators are deliberately
    absent because they obtain replacement outbound credentials; this chain
    forwards only the original user bearer.
      GATEWAY_URL       — lane-configured target-specific Gateway MCP URL
      SKILL_REGISTRY_ID — AgentCore Registry ID for skill records
"""

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from mcp.client.streamable_http import streamablehttp_client
from sage_identity import (
    AUTHORIZATION_HEADER,
    CORRELATION_HEADER,
    AuthenticationArtifact,
    CorrelationId,
    IdentityError,
    IdentityErrorCode,
    build_authorization_transport,
    build_correlation_headers,
    parse_bearer_authorization,
    serialize_identity_error,
    serialize_log_fields,
    serialize_safe_fields,
)
from strands import Agent, AgentSkills, Skill
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"

GATEWAY_URL = os.environ.get("GATEWAY_URL")
SKILL_REGISTRY_ID = os.environ.get("SKILL_REGISTRY_ID")
REGION = os.environ.get("AWS_REGION", "us-east-1")


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
        except Exception as error:
            logger.warning(
                "Failed to load skill record %s (%s): %s",
                record_id,
                record_name,
                error,
            )

    return skills


if not SKILL_REGISTRY_ID:
    raise RuntimeError(
        "SKILL_REGISTRY_ID environment variable is required. "
        "Run 'uv run python scripts/deploy_registry.py' to create the registry, "
        "then set SKILL_REGISTRY_ID to the registry ID."
    )

_skills = _fetch_skills_from_registry(SKILL_REGISTRY_ID)
logger.info("AgentSkills plugin initialized with %d skills from registry", len(_skills))
_skills_plugin = AgentSkills(skills=cast(Any, _skills))


def _header_values(
    request_headers: Mapping[str, object], header_name: str
) -> tuple[object, ...]:
    values: list[object] = []
    for name, value in request_headers.items():
        if name.casefold() != header_name.casefold():
            continue
        if isinstance(value, (list, tuple)):
            values.extend(value)
        else:
            values.append(value)
    return tuple(values)


def _parse_invocation_transport(
    request_headers: Mapping[str, object],
) -> tuple[AuthenticationArtifact, CorrelationId]:
    correlation_values = _header_values(request_headers, CORRELATION_HEADER)
    if not correlation_values:
        correlation_id = CorrelationId.new()
    elif len(correlation_values) == 1 and isinstance(correlation_values[0], str):
        try:
            correlation_id = CorrelationId(correlation_values[0])
        except ValueError as error:
            raise IdentityError(
                IdentityErrorCode.IDENTITY_INVALID, CorrelationId.new()
            ) from error
    else:
        raise IdentityError(IdentityErrorCode.IDENTITY_INVALID, CorrelationId.new())

    bearer = parse_bearer_authorization(
        _header_values(request_headers, AUTHORIZATION_HEADER), correlation_id
    )
    return bearer, correlation_id


def _is_expiry_failure(error: BaseException) -> bool:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, IdentityError):
            if current.code is IdentityErrorCode.SESSION_EXPIRED:
                return True
        response = getattr(current, "response", None)
        if getattr(response, "status_code", None) == 401:
            return True
        if getattr(current, "status_code", None) == 401:
            return True
        for nested in (
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
        nested_group = getattr(current, "exceptions", ())
        if isinstance(nested_group, tuple):
            pending.extend(
                nested for nested in nested_group if isinstance(nested, BaseException)
            )
    return False


def _make_mcp_client(
    bearer: AuthenticationArtifact, correlation_id: CorrelationId
) -> MCPClient:
    """Create a Gateway MCP client using only trusted bearer transport."""
    gateway_url = GATEWAY_URL
    if not gateway_url:
        raise RuntimeError("GATEWAY_URL is required")

    headers = build_authorization_transport(bearer).as_headers()
    headers.update(build_correlation_headers(correlation_id))
    return MCPClient(lambda: streamablehttp_client(gateway_url, headers=headers))


def _build_model_input(payload: Mapping[str, object], correlation_id: CorrelationId) -> str:
    try:
        safe_fields = serialize_safe_fields(
            {"prompt": payload.get("prompt", "Hello")}
        )
    except (TypeError, ValueError) as error:
        raise IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation_id) from error
    prompt = safe_fields.get("prompt")
    if not isinstance(prompt, str):
        raise IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation_id)
    return prompt


_STREAM_EVENT_KEYS = ("data", "current_tool_use", "delta", "message", "event")


def _serialize_stream_event(
    event: object, correlation_id: CorrelationId
) -> dict[str, object]:
    """Project one Strands event onto the safe client contract, then sanitize.

    Strands attaches internal objects to every streamed event (``agent``,
    ``event_loop_cycle_id``, ``event_loop_cycle_trace``, ``event_loop_cycle_span``,
    ``request_state``). None of them belong on the wire, and the strict field
    sanitizer rejects them outright, so they are dropped here rather than
    aborting the invocation. Only the keys the client actually renders survive,
    plus the terminal ``stop_reason``.
    """
    if not isinstance(event, Mapping):
        raise IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation_id)
    projected: dict[str, object] = {
        key: event[key] for key in _STREAM_EVENT_KEYS if key in event
    }
    stop_reason = getattr(event.get("result"), "stop_reason", None)
    if isinstance(stop_reason, str):
        projected["result"] = {"stop_reason": stop_reason}
    try:
        return cast(dict[str, object], serialize_safe_fields(projected))
    except (TypeError, ValueError) as error:
        raise IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation_id) from error


def _log_invocation_failure(error: IdentityError) -> None:
    safe_fields = serialize_log_fields(
        {
            "code": error.code.value,
            "correlation_id": error.correlation_id,
        }
    )
    logger.warning(
        "Agent invocation failed",
        extra={"identity_error": safe_fields},
    )


@app.entrypoint
async def invoke(payload: dict, context: RequestContext):
    """Process a user message and stream provenance-safe response events.

    Args:
        payload: Dict with an optional safe ``prompt`` field.
        context: AgentCore request context providing Runtime-forwarded headers.

    Yields:
        Sanitized stream events or one stable non-secret failure result.
    """
    try:
        bearer, correlation_id = _parse_invocation_transport(
            context.request_headers or {}
        )
    except IdentityError as error:
        _log_invocation_failure(error)
        yield serialize_identity_error(error)
        return

    try:
        user_message = _build_model_input(payload, correlation_id)
        with _make_mcp_client(bearer, correlation_id) as mcp_client:
            tools = mcp_client.list_tools_sync()
            agent = Agent(
                model=model,
                system_prompt=_load_base_prompt(),
                plugins=[_skills_plugin],
                tools=tools,
            )
            async for event in agent.stream_async(user_message):
                serialized = _serialize_stream_event(event, correlation_id)
                if serialized:
                    yield serialized
    except IdentityError as error:
        _log_invocation_failure(error)
        yield serialize_identity_error(error)
    except Exception as error:
        safe_error = IdentityError(
            IdentityErrorCode.SESSION_EXPIRED
            if _is_expiry_failure(error)
            else IdentityErrorCode.REQUEST_FAILED,
            correlation_id,
        )
        _log_invocation_failure(safe_error)
        yield serialize_identity_error(safe_error)


if __name__ == "__main__":
    app.run()
