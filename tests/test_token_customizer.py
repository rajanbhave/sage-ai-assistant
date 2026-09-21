import json

import pytest

from sage_identity import AccessTokenCustomizerConfiguration, AuthorizedScopeGrant, CorrelationId, IdentityError, customize_access_token, lambda_handler


def config():
    return AccessTokenCustomizerConfiguration(
        "pool", "Tenant_A", "custom:tenant_id", "tenant", frozenset({"client"}),
        (AuthorizedScopeGrant("subject", "client", frozenset({"sage-agent/invoke", "sage-api/read"})),),
    )


def event(scopes):
    return {"version": "2", "userPoolId": "pool", "callerContext": {"clientId": "client"}, "request": {"userAttributes": {"sub": "subject", "tenant": "Tenant_A"}, "scopes": scopes}}


def test_customizer_emits_exact_authorized_scope_delta_and_tenant():
    result = customize_access_token(event(["openid", "profile"]), config())
    override = result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]
    assert override["claimsToAddOrOverride"] == {"custom:tenant_id": "Tenant_A"}
    assert override["scopesToAdd"] == ["sage-agent/invoke", "sage-api/read"]
    assert override["scopesToSuppress"] == ["openid", "profile"]


def test_customizer_rejects_caller_tenant_override():
    candidate = event([])
    candidate["request"]["clientMetadata"] = {"custom:tenant_id": "Tenant_B"}
    with pytest.raises(IdentityError):
        customize_access_token(candidate, config())


def test_lambda_handler_loads_immutable_lane_configuration(monkeypatch):
    monkeypatch.setenv(
        "SAGE_TOKEN_CUSTOMIZER_CONFIG",
        json.dumps(
            {
                "userPoolId": "pool",
                "expectedTenant": "Tenant_A",
                "canonicalTenantClaimName": "custom:tenant_id",
                "trustedAssignmentAttribute": "tenant",
                "trustedClientIds": ["client"],
                "scopeGrants": [
                    {
                        "subject": "subject",
                        "clientId": "client",
                        "scopes": ["sage-agent/invoke", "sage-api/read"],
                    }
                ],
            }
        ),
    )

    result = lambda_handler(event([]), object())

    override = result["response"]["claimsAndScopeOverrideDetails"][
        "accessTokenGeneration"
    ]
    assert override["claimsToAddOrOverride"] == {
        "custom:tenant_id": "Tenant_A"
    }
