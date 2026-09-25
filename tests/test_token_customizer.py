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


def test_customizer_emits_the_same_tenant_claim_on_both_token_types():
    """Access token is the bearer; ID-token readers must not see an absent claim."""
    details = customize_access_token(event([]), config())["response"][
        "claimsAndScopeOverrideDetails"
    ]

    assert details["idTokenGeneration"]["claimsToAddOrOverride"] == {
        "custom:tenant_id": "Tenant_A"
    }
    assert (
        details["idTokenGeneration"]["claimsToAddOrOverride"]
        == details["accessTokenGeneration"]["claimsToAddOrOverride"]
    )
    # Scope authority belongs to the access token alone.
    assert "scopesToAdd" not in details["idTokenGeneration"]
    assert "scopesToSuppress" not in details["idTokenGeneration"]


def test_customizer_honours_a_foreign_canonical_tenant_claim_name():
    """The claim name is configuration, so another deployment needs no rename."""
    foreign = AccessTokenCustomizerConfiguration(
        "pool", "Tenant_A", "custom:tenant_slug", "tenant", frozenset({"client"}),
        (AuthorizedScopeGrant("subject", "client", frozenset({"sage-api/read"})),),
    )

    details = customize_access_token(event([]), foreign)["response"][
        "claimsAndScopeOverrideDetails"
    ]

    for generation in ("accessTokenGeneration", "idTokenGeneration"):
        assert details[generation]["claimsToAddOrOverride"] == {
            "custom:tenant_slug": "Tenant_A"
        }


@pytest.mark.parametrize("owned", ["iss", "exp", "sub", "client_id", "token_use"])
def test_customizer_refuses_a_cognito_owned_canonical_claim_name(owned):
    with pytest.raises(ValueError):
        AccessTokenCustomizerConfiguration(
            "pool", "Tenant_A", owned, "tenant", frozenset({"client"}),
            (AuthorizedScopeGrant("subject", "client", frozenset({"sage-api/read"})),),
        )


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
