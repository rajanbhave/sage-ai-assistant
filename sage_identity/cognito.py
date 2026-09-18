"""Cognito V2 access-token customization for one trusted tenant lane."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Never, TypeGuard, cast

from .models import TENANT_A, TENANT_B
from .transport import CorrelationId, IdentityError, IdentityErrorCode

SAGE_SCOPE_PROFILE = frozenset(
    {
        "sage-agent/invoke",
        "sage-gateway/invoke",
        "sage-mcp/invoke",
        "sage-api/read",
    }
)
_COGNITO_OWNED_CLAIMS = frozenset(
    {"iss", "exp", "sub", "client_id", "token_use"}
)


@dataclass(frozen=True, slots=True)
class AuthorizedScopeGrant:
    """Sage scopes administratively authorized for one subject and client."""

    subject: str
    client_id: str
    scopes: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scopes", frozenset(self.scopes))
        if not _non_empty(self.subject) or not _non_empty(self.client_id):
            raise ValueError("scope grant subject and client must be non-empty")
        if not self.scopes or not self.scopes <= SAGE_SCOPE_PROFILE:
            raise ValueError("scope grants must contain only Sage scopes")


@dataclass(frozen=True, slots=True)
class AccessTokenCustomizerConfiguration:
    """Immutable trusted inputs for one lane's access-token customizer."""

    user_pool_id: str
    expected_tenant: str
    canonical_tenant_claim_name: str
    trusted_assignment_attribute: str
    trusted_client_ids: frozenset[str]
    scope_grants: tuple[AuthorizedScopeGrant, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "trusted_client_ids", frozenset(self.trusted_client_ids))
        object.__setattr__(self, "scope_grants", tuple(self.scope_grants))
        if any(
            not _non_empty(value)
            for value in (
                self.user_pool_id,
                self.expected_tenant,
                self.canonical_tenant_claim_name,
                self.trusted_assignment_attribute,
            )
        ):
            raise ValueError("customizer configuration values must be non-empty")
        if self.canonical_tenant_claim_name in _COGNITO_OWNED_CLAIMS:
            raise ValueError("canonical tenant claim cannot replace a Cognito-owned claim")
        if self.expected_tenant not in {TENANT_A, TENANT_B}:
            raise ValueError("customizer tenant must be Tenant_A or Tenant_B")
        if not self.trusted_client_ids or not self.scope_grants:
            raise ValueError("customizer requires trusted clients and scope grants")
        grant_keys = {(grant.subject, grant.client_id) for grant in self.scope_grants}
        if len(grant_keys) != len(self.scope_grants):
            raise ValueError("scope grants must be unique per subject and client")
        if any(grant.client_id not in self.trusted_client_ids for grant in self.scope_grants):
            raise ValueError("scope grant client must be trusted by the lane")


def load_access_token_customizer_configuration(
    serialized: str,
) -> AccessTokenCustomizerConfiguration:
    """Load immutable, non-secret authorization configuration for the Lambda."""
    try:
        raw = json.loads(serialized)
        if not isinstance(raw, Mapping):
            raise ValueError("configuration must be an object")
        grants_value = raw.get("scopeGrants")
        if not isinstance(grants_value, list):
            raise ValueError("scopeGrants must be a list")
        grants = tuple(
            AuthorizedScopeGrant(
                subject=_required_string(grant, "subject"),
                client_id=_required_string(grant, "clientId"),
                scopes=_string_set(grant.get("scopes"), "scopes"),
            )
            for grant_value in grants_value
            for grant in [_string_mapping(grant_value, "scopeGrant")]
        )
        return AccessTokenCustomizerConfiguration(
            user_pool_id=_required_string(raw, "userPoolId"),
            expected_tenant=_required_string(raw, "expectedTenant"),
            canonical_tenant_claim_name=_required_string(
                raw, "canonicalTenantClaimName"
            ),
            trusted_assignment_attribute=_required_string(
                raw, "trustedAssignmentAttribute"
            ),
            trusted_client_ids=_string_set(
                raw.get("trustedClientIds"), "trustedClientIds"
            ),
            scope_grants=grants,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid token customizer configuration") from error


def lambda_handler(event: object, _context: object) -> dict[str, Any]:
    """AWS Lambda entrypoint for Cognito V2 pre-token generation."""
    if not isinstance(event, Mapping):
        _reject()
    try:
        configuration = load_access_token_customizer_configuration(
            os.environ["SAGE_TOKEN_CUSTOMIZER_CONFIG"]
        )
    except (KeyError, ValueError):
        _reject()
    return customize_access_token(cast(Mapping[str, object], event), configuration)


def customize_access_token(
    event: Mapping[str, object],
    configuration: AccessTokenCustomizerConfiguration,
) -> dict[str, Any]:
    """Return a V2 event with one trusted tenant claim and exact authorized scopes.

    Args:
        event: Cognito pre-token-generation event version 2.
        configuration: Trusted deployment configuration for the issuing lane.

    Returns:
        A copy of ``event`` containing access-token claim and scope overrides.

    Raises:
        IdentityError: If the event is not bound to one valid lane assignment,
            subject, client, or authorized scope grant.
    """
    if event.get("version") != "2" or event.get("userPoolId") != configuration.user_pool_id:
        _reject()

    request = _mapping(event.get("request"))
    caller_context = _mapping(event.get("callerContext"))
    attributes = _mapping(request.get("userAttributes"))
    metadata = _mapping(request.get("clientMetadata", {}))
    client_id = caller_context.get("clientId")
    subject = attributes.get("sub")
    tenant = attributes.get(configuration.trusted_assignment_attribute)

    if (
        not _non_empty(client_id)
        or client_id not in configuration.trusted_client_ids
        or not _non_empty(subject)
        or not _non_empty(tenant)
        or tenant != configuration.expected_tenant
    ):
        _reject()

    override_keys = {
        configuration.canonical_tenant_claim_name,
        configuration.trusted_assignment_attribute,
    }
    if any(key in metadata for key in override_keys):
        _reject()

    grants = [
        grant
        for grant in configuration.scope_grants
        if grant.subject == subject and grant.client_id == client_id
    ]
    if len(grants) != 1:
        _reject()
    authorized_scopes = grants[0].scopes

    incoming_scopes = _scope_set(request.get("scopes"))
    result: dict[str, Any] = deepcopy(dict(event))
    result["response"] = {
        "claimsAndScopeOverrideDetails": {
            "accessTokenGeneration": {
                "claimsToAddOrOverride": {
                    configuration.canonical_tenant_claim_name: tenant,
                },
                "scopesToAdd": sorted(authorized_scopes - incoming_scopes),
                "scopesToSuppress": sorted(incoming_scopes - authorized_scopes),
            }
        }
    }
    return result


def _string_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _required_string(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not _non_empty(value):
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _string_set(value: object, field: str) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a string list")
    result = frozenset(item for item in value if _non_empty(item))
    if not result or len(result) != len(value):
        raise ValueError(f"{field} must contain non-empty strings")
    return result


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _reject()
    return cast(Mapping[str, object], value)


def _scope_set(value: object) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _reject()
    scopes: list[str] = []
    for scope in value:
        if not _non_empty(scope) or any(char.isspace() for char in scope):
            _reject()
        scopes.append(scope)
    return frozenset(scopes)


def _non_empty(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _reject() -> Never:
    raise IdentityError(IdentityErrorCode.TOKEN_ISSUANCE_REJECTED, CorrelationId.new())
