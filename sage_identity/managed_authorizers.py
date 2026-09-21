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
) -> dict[str, dict[str, Any]]:
    """Render the three managed JWT authorizers for one tenant lane.

    Args:
        lane: Trusted immutable configuration for the hosting tenant lane.

    Returns:
        Agent Runtime, Gateway, and MCP Runtime authorizer payloads keyed by
        managed-door name.
    """
    return {
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
