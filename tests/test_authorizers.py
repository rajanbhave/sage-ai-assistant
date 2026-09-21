from sage_identity import (
    TENANT_A,
    TENANT_B,
    ManagedDoor,
    TenantLaneConfiguration,
    render_lane_authorizers,
)
from scripts.deploy_gateway import apply_gateway_authorizer


def test_each_lane_managed_door_enforces_its_full_local_policy():
    scopes = {
        ManagedDoor.AGENT_RUNTIME: "sage-agent/invoke",
        ManagedDoor.GATEWAY: "sage-gateway/invoke",
        ManagedDoor.MCP_RUNTIME: "sage-mcp/invoke",
    }
    for tenant in (TENANT_A, TENANT_B):
        lane = TenantLaneConfiguration(
            tenant,
            tenant,
            f"pool-{tenant}",
            f"https://issuer/{tenant}",
            f"https://issuer/{tenant}/.well-known/openid-configuration",
            frozenset({f"client-{tenant}"}),
            f"agent-endpoint-{tenant}",
            f"agent-{tenant}",
            f"gateway-{tenant}",
            f"gateway-endpoint-{tenant}",
            f"mcp-{tenant}",
            tenant,
        )
        rendered = render_lane_authorizers(lane)

        assert set(rendered) == {door.value for door in ManagedDoor}
        for door, scope in scopes.items():
            auth = rendered[door.value]["customJWTAuthorizer"]
            assert auth["discoveryUrl"] == lane.discovery_url
            assert auth["allowedClients"] == [f"client-{tenant}"]
            assert auth["allowedScopes"] == [scope]
            assert auth["customClaims"] == [
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
                        "claimMatchValue": {"matchValueString": tenant},
                    },
                },
            ]


def test_gateway_deployment_applies_and_verifies_managed_authorizer():
    authorizer = render_lane_authorizers(
        TenantLaneConfiguration(
            TENANT_A,
            TENANT_A,
            "pool-a",
            "https://issuer/a",
            "https://issuer/a/.well-known/openid-configuration",
            frozenset({"client-a"}),
            "agent-endpoint-a",
            "agent-a",
            "gateway-a",
            "gateway-endpoint-a",
            "mcp-a",
            TENANT_A,
        )
    )[ManagedDoor.GATEWAY.value]

    class Client:
        def __init__(self):
            self.update = None

        def get_gateway(self, **_kwargs):
            return {
                "name": "sage-gateway-a",
                "roleArn": "arn:aws:iam::123456789012:role/gateway-a",
                "protocolType": "MCP",
                "authorizerType": "CUSTOM_JWT" if self.update else "NONE",
                "authorizerConfiguration": authorizer if self.update else None,
            }

        def update_gateway(self, **request):
            self.update = request
            return request

    client = Client()
    apply_gateway_authorizer(client, "gateway-a", authorizer)

    assert client.update == {
        "gatewayIdentifier": "gateway-a",
        "name": "sage-gateway-a",
        "roleArn": "arn:aws:iam::123456789012:role/gateway-a",
        "protocolType": "MCP",
        "authorizerType": "CUSTOM_JWT",
        "authorizerConfiguration": authorizer,
    }
