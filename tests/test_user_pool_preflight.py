import json
from dataclasses import replace

import pytest

from scripts.deploy_user_pool import LaneInput, _verify_pre_token_customizer


def lane() -> LaneInput:
    return LaneInput(
        lane_id="Tenant_A",
        tenant_id="Tenant_A",
        user_pool_id="pool-a",
        client_name="client-a",
        expected_tenant_claim="Tenant_A",
        trusted_assignment_attribute="custom:tenant",
        pre_token_lambda_arn=(
            "arn:aws:lambda:us-east-1:123456789012:function:sage-token-a:live"
        ),
        pre_token_lambda_code_sha256="approved-code-hash",
        agent_runtime_endpoint="https://agent.example/invocations",
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
                                "userPoolId": "pool-a",
                                "expectedTenant": "Tenant_A",
                                "canonicalTenantClaimName": "custom:tenant_id",
                                "trustedAssignmentAttribute": "custom:tenant",
                                "trustedClientIds": ["client-id-a"],
                                "scopeGrants": [
                                    {
                                        "subject": "subject-a",
                                        "clientId": "client-id-a",
                                        "scopes": ["sage-agent/invoke"],
                                    }
                                ],
                            }
                        )
                    }
                },
            }
        }


def test_preflight_verifies_qualified_code_and_lane_configuration():
    assert (
        _verify_pre_token_customizer(LambdaClient(), lane(), "client-id-a")
        == "approved-code-hash"
    )

    with pytest.raises(ValueError, match="code identity"):
        _verify_pre_token_customizer(
            LambdaClient(),
            replace(lane(), pre_token_lambda_code_sha256="wrong"),
            "client-id-a",
        )

    with pytest.raises(ValueError, match="immutable version or alias"):
        _verify_pre_token_customizer(
            LambdaClient(),
            replace(
                lane(),
                pre_token_lambda_arn=(
                    "arn:aws:lambda:us-east-1:123456789012:function:sage-token-a"
                ),
            ),
            "client-id-a",
        )
