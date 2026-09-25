import json
from dataclasses import replace

import pytest

from scripts.deploy_user_pool import (
    LaneInput,
    _verify_pre_token_customizer,
    verify_lane_preflight,
)
from tests.env import topology

POOL_ID = topology("SAGE_TEST_TENANT_A_USER_POOL_ID")
CLIENT_ID = topology("SAGE_TEST_TENANT_A_CLIENT_ID")
ALIAS_ARN = topology("SAGE_TEST_TENANT_A_PRE_TOKEN_LAMBDA_ARN")
AGENT_ENDPOINT = topology("SAGE_TEST_TENANT_A_AGENT_RUNTIME_ENDPOINT")


def lane() -> LaneInput:
    return LaneInput(
        lane_id="Tenant_A",
        tenant_id="Tenant_A",
        user_pool_id=POOL_ID,
        client_name="client-a",
        expected_tenant_claim="Tenant_A",
        trusted_assignment_attribute="custom:tenant",
        pre_token_lambda_arn=ALIAS_ARN,
        pre_token_lambda_code_sha256="approved-code-hash",
        agent_runtime_endpoint=AGENT_ENDPOINT,
        approved_access_token_validity=60,
        approved_access_token_validity_unit="minutes",
        token_lifetime_approval_reference="approval-1",
    )


class LambdaClient:
    def get_function(self, **_kwargs):
        return {
            "Configuration": {
                "Handler": "sage_identity.cognito.lambda_handler",
                "Version": "7",
                "CodeSha256": "approved-code-hash",
                "Environment": {
                    "Variables": {
                        "SAGE_TOKEN_CUSTOMIZER_CONFIG": json.dumps(
                            {
                                "userPoolId": POOL_ID,
                                "expectedTenant": "Tenant_A",
                                "canonicalTenantClaimName": "custom:tenant_id",
                                "trustedAssignmentAttribute": "custom:tenant",
                                "trustedClientIds": [CLIENT_ID],
                                "scopeGrants": [
                                    {
                                        "subject": "subject-a",
                                        "clientId": CLIENT_ID,
                                        "scopes": ["sage-agent/invoke"],
                                    }
                                ],
                            }
                        )
                    }
                },
            }
        }


class Cognito:
    """Minimal describe-only stub for the preflight feature-plan gate."""

    def __init__(self, tier: str, lambda_version: str) -> None:
        self._tier = tier
        self._lambda_version = lambda_version

    def describe_user_pool(self, UserPoolId: str):  # noqa: N803 - boto3 casing
        return {
            "UserPool": {
                "Id": UserPoolId,
                "UserPoolTier": self._tier,
                "LambdaConfig": {
                    "PreTokenGenerationConfig": {
                        "LambdaVersion": self._lambda_version,
                        "LambdaArn": lane().pre_token_lambda_arn,
                    }
                },
            }
        }


def test_preflight_rejects_a_plan_that_cannot_deliver_v2_events():
    """A Lite pool customizes only the ID token, so the bearer loses its tenant."""
    with pytest.raises(ValueError) as rejected:
        verify_lane_preflight(Cognito("LITE", "V1_0"), LambdaClient(), lane())

    message = str(rejected.value)
    assert "cannot deliver V2_0 pre-token events" in message
    assert "not the access token" in message
    assert "--user-pool-tier ESSENTIALS" in message


def test_preflight_accepts_the_legacy_lite_pool_exception():
    """Pools with V2_0 already active on Lite predate the plan requirement."""
    with pytest.raises(ValueError) as rejected:
        verify_lane_preflight(Cognito("LITE", "V2_0"), LambdaClient(), lane())

    # Fails later on the assignment source, not at the feature-plan gate.
    assert "feature plan" not in str(rejected.value)


def test_preflight_rejects_a_v1_trigger_on_a_supported_plan():
    with pytest.raises(ValueError, match="cannot add claims to an access token"):
        verify_lane_preflight(Cognito("ESSENTIALS", "V1_0"), LambdaClient(), lane())


def test_preflight_verifies_qualified_code_and_lane_configuration():
    assert (
        _verify_pre_token_customizer(LambdaClient(), lane(), CLIENT_ID)
        == "approved-code-hash"
    )

    with pytest.raises(ValueError, match="code identity"):
        _verify_pre_token_customizer(
            LambdaClient(),
            replace(lane(), pre_token_lambda_code_sha256="wrong"),
            CLIENT_ID,
        )

    with pytest.raises(ValueError, match="immutable version or alias"):
        _verify_pre_token_customizer(
            LambdaClient(),
            replace(lane(), pre_token_lambda_arn=ALIAS_ARN.rsplit(":", 1)[0]),
            CLIENT_ID,
        )
