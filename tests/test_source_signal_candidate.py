"""The AgentCore Runtime target candidate for restricting the MCP Runtime source.

AWS documents that JWT_PASSTHROUGH is available for HTTP passthrough *and*
AgentCore Runtime targets, and that allowedWorkloadConfiguration is supported only
for AgentCore Runtime targets with Gateways as the allowed workloads. These tests
pin the rendered shape. Nothing here applies anything.
"""

import pytest

from sage_identity import TENANT_A, TenantLaneConfiguration, render_lane_authorizers
from scripts.deploy_gateway import render_runtime_target_candidate
from tests.env import lane_topology, topology

GATEWAY_ARN = topology("SAGE_TEST_TENANT_A_GATEWAY_ARN")
RUNTIME_ARN = topology("SAGE_TEST_TENANT_A_MCP_RUNTIME_ARN")
REGION = topology("SAGE_TEST_REGION")


def lane() -> TenantLaneConfiguration:
    pool_id = topology("SAGE_TEST_TENANT_A_USER_POOL_ID")
    issuer = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}"
    return TenantLaneConfiguration(
        lane_id=TENANT_A,
        tenant_id=TENANT_A,
        user_pool_id=pool_id,
        issuer=issuer,
        discovery_url=f"{issuer}/.well-known/openid-configuration",
        frontend_client_ids=frozenset({topology("SAGE_TEST_TENANT_A_CLIENT_ID")}),
        agent_runtime_endpoint=topology(
            "SAGE_TEST_TENANT_A_AGENT_RUNTIME_ENDPOINT"
        ),
        agent_runtime_id=topology("SAGE_TEST_TENANT_A_AGENT_RUNTIME_ID"),
        gateway_id=topology("SAGE_TEST_TENANT_A_GATEWAY_ID"),
        gateway_target_url=topology("SAGE_TEST_TENANT_A_GATEWAY_TARGET_URL"),
        mcp_runtime_id=topology("SAGE_TEST_TENANT_A_MCP_RUNTIME_ID"),
        expected_tenant_claim=TENANT_A,
    )


def configuration(**lane_overrides):
    record = lane_topology(TENANT_A)
    record.update(lane_overrides)
    return {"region": REGION, "lanes": [record]}


def test_authorizers_omit_the_workload_restriction_by_default():
    """The deployed passthrough topology cannot claim a Gateway source signal."""
    rendered = render_lane_authorizers(lane())

    for door in rendered.values():
        assert "allowedWorkloadConfiguration" not in door["customJWTAuthorizer"]


def test_only_the_mcp_runtime_authorizer_gains_the_allowed_gateway():
    rendered = render_lane_authorizers(lane(), mcp_allowed_gateway_arn=GATEWAY_ARN)

    assert rendered["mcp_runtime"]["customJWTAuthorizer"][
        "allowedWorkloadConfiguration"
    ] == {"hostingEnvironments": [{"arn": GATEWAY_ARN}]}
    for door in ("agent_runtime", "gateway"):
        assert (
            "allowedWorkloadConfiguration"
            not in rendered[door]["customJWTAuthorizer"]
        )


def test_an_empty_allowed_gateway_arn_is_refused():
    with pytest.raises(ValueError):
        render_lane_authorizers(lane(), mcp_allowed_gateway_arn="  ")


def test_runtime_target_candidate_uses_arn_and_qualifier_not_a_composed_url():
    """The gateway resolves the runtime endpoint itself for a Runtime target."""
    candidate = render_runtime_target_candidate(configuration())[0]

    assert candidate["targetConfiguration"] == {
        "http": {"agentcoreRuntime": {"arn": RUNTIME_ARN, "qualifier": "DEFAULT"}}
    }
    assert candidate["credentialProviderConfigurations"] == [
        {"credentialProviderType": "JWT_PASSTHROUGH"}
    ]


def test_runtime_target_candidate_records_a_missing_gateway_arn_as_unavailable():
    """Without the Gateway ARN the allowed workload cannot be claimed."""
    candidate = render_runtime_target_candidate(configuration())[0]
    assert "unavailable" in candidate["mcpRuntimeAuthorizerAddition"]

    with_arn = render_runtime_target_candidate(
        configuration(gatewayArn=GATEWAY_ARN)
    )[0]
    assert with_arn["mcpRuntimeAuthorizerAddition"] == {
        "allowedWorkloadConfiguration": {
            "hostingEnvironments": [{"arn": GATEWAY_ARN}]
        }
    }
