"""Same-lane AgentCore JWT authorizer rendering."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Final

from .models import ManagedDoor, TenantLaneConfiguration

REQUIRED_DOOR_SCOPES: Final = MappingProxyType(
    {
        ManagedDoor.AGENT_RUNTIME: "sage-agent/invoke",
        ManagedDoor.GATEWAY: "sage-gateway/invoke",
        ManagedDoor.MCP_RUNTIME: "sage-mcp/invoke",
    }
)


def render_lane_authorizers(
    lane: TenantLaneConfiguration,
    *,
    mcp_allowed_gateway_arn: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Render the three managed JWT authorizers for one tenant lane.

    Args:
        lane: Trusted immutable configuration for the hosting tenant lane.
        mcp_allowed_gateway_arn: When set, restrict the MCP Runtime authorizer to
            that Gateway as the only allowed workload in the request identity
            chain. AWS documents ``allowedWorkloadConfiguration`` as supported
            only for AgentCore Runtime targets, with AgentCore Gateways as the
            allowed workloads, so this is rendered only for a Runtime-target
            topology and is omitted by default.

    Returns:
        Agent Runtime, Gateway, and MCP Runtime authorizer payloads keyed by
        managed-door name.
    """
    authorizers = {
        door.value: {
            "customJWTAuthorizer": {
                "discoveryUrl": lane.discovery_url,
                "allowedClients": sorted(lane.frontend_client_ids),
                "allowedScopes": [scope],
                "customClaims": [
                    {
                        "inboundTokenClaimName": "token_use",
                        "inboundTokenClaimValueType": "STRING",
                        "authorizingClaimMatchValue": {
                            "claimMatchOperator": "EQUALS",
                            "claimMatchValue": {"matchValueString": "access"},
                        },
                    },
                    {
                        "inboundTokenClaimName": "custom:tenant_id",
                        "inboundTokenClaimValueType": "STRING",
                        "authorizingClaimMatchValue": {
                            "claimMatchOperator": "EQUALS",
                            "claimMatchValue": {
                                "matchValueString": lane.expected_tenant_claim
                            },
                        },
                    },
                ],
            }
        }
        for door, scope in REQUIRED_DOOR_SCOPES.items()
    }
    if mcp_allowed_gateway_arn is not None:
        if not mcp_allowed_gateway_arn.strip():
            raise ValueError("allowed Gateway ARN must be non-empty when provided")
        authorizers[ManagedDoor.MCP_RUNTIME.value]["customJWTAuthorizer"][
            "allowedWorkloadConfiguration"
        ] = {"hostingEnvironments": [{"arn": mcp_allowed_gateway_arn}]}
    return authorizers
