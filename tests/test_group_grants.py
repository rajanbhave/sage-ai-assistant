"""Group-based scope grants in the Cognito access-token customizer."""

import json

import pytest

from sage_identity import (
    AccessTokenCustomizerConfiguration,
    AuthorizedScopeGrant,
    IdentityError,
    customize_access_token,
    load_access_token_customizer_configuration,
)

SUBJECT_GRANT = AuthorizedScopeGrant(
    "subject", "client", frozenset({"sage-api/read"})
)


def config(**overrides):
    base = {
        "user_pool_id": "pool",
        "expected_tenant": "Tenant_A",
        "canonical_tenant_claim_name": "custom:tenant_id",
        "trusted_assignment_attribute": "tenant",
        "trusted_client_ids": frozenset({"client"}),
        "scope_grants": (SUBJECT_GRANT,),
    }
    base.update(overrides)
    return AccessTokenCustomizerConfiguration(**base)


def event(groups=None):
    request = {
        "userAttributes": {"sub": "subject", "tenant": "Tenant_A"},
        "scopes": [],
    }
    if groups is not None:
        request["groupConfiguration"] = {"groupsToOverride": groups}
    return {
        "version": "2",
        "userPoolId": "pool",
        "callerContext": {"clientId": "client"},
        "request": request,
    }


def scopes_added(result):
    return set(
        result["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"][
            "scopesToAdd"
        ]
    )


def test_group_scopes_union_with_the_subject_grant():
    result = customize_access_token(
        event(["sage-operators"]),
        config(group_grants={"sage-operators": frozenset({"sage-agent/invoke"})}),
    )

    assert scopes_added(result) == {"sage-api/read", "sage-agent/invoke"}


def test_subject_grant_remains_the_fallback_when_no_group_matches():
    """Existing deployments carry no groups and must behave exactly as before."""
    grants = {"sage-operators": frozenset({"sage-agent/invoke"})}

    assert scopes_added(
        customize_access_token(event(["unrelated-group"]), config(group_grants=grants))
    ) == {"sage-api/read"}
    assert scopes_added(
        customize_access_token(event(None), config(group_grants=grants))
    ) == {"sage-api/read"}
    assert scopes_added(customize_access_token(event(None), config())) == {
        "sage-api/read"
    }


def test_group_grants_alone_authorize_a_subject_with_no_subject_grant():
    result = customize_access_token(
        event(["sage-operators"]),
        config(
            scope_grants=(),
            group_grants={"sage-operators": frozenset({"sage-mcp/invoke"})},
        ),
    )

    assert scopes_added(result) == {"sage-mcp/invoke"}


def test_a_subject_with_neither_grant_is_rejected():
    with pytest.raises(IdentityError):
        customize_access_token(
            event(["unrelated-group"]),
            config(
                scope_grants=(),
                group_grants={"sage-operators": frozenset({"sage-mcp/invoke"})},
            ),
        )


def test_group_grants_must_name_only_sage_scopes():
    with pytest.raises(ValueError):
        config(group_grants={"sage-operators": frozenset({"admin/everything"})})


def test_group_grants_load_from_configuration_json():
    loaded = load_access_token_customizer_configuration(
        json.dumps(
            {
                "userPoolId": "pool",
                "expectedTenant": "Tenant_A",
                "canonicalTenantClaimName": "custom:tenant_id",
                "trustedAssignmentAttribute": "tenant",
                "trustedClientIds": ["client"],
                "groupGrants": {"sage-operators": ["sage-mcp/invoke"]},
            }
        )
    )

    assert loaded.group_grants == {"sage-operators": frozenset({"sage-mcp/invoke"})}
    assert loaded.scope_grants == ()
