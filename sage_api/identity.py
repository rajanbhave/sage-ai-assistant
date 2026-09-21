"""Exact issuer selection and independent access-token validation for Sage API."""

from __future__ import annotations

import base64
import binascii
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass

import jwt

from sage_identity import (
    AllowedTenantIssuerMap,
    ApiIssuerConfiguration,
    CorrelationId,
    IdentityError,
    IdentityErrorCode,
    TENANT_A,
    TENANT_B,
)

CANONICAL_TENANT_CLAIM = "custom:tenant_id"
_REQUIRED_TENANTS = frozenset({TENANT_A, TENANT_B})


class _JsonObject(tuple[tuple[str, object], ...]):
    """JSON object represented as ordered pairs so duplicate keys survive."""


@dataclass(frozen=True, slots=True)
class VerifiedApiIdentity:
    """Identity created only after complete independent token validation."""

    issuer: str
    subject: str
    tenant_id: str
    client_id: str
    scopes: frozenset[str]


def select_issuer_configuration(
    encoded_jwt: str,
    allowed_issuers: AllowedTenantIssuerMap,
    correlation_id: CorrelationId,
) -> ApiIssuerConfiguration:
    """Select one immutable validation configuration by exact unverified issuer."""
    try:
        entries = _validated_entries(allowed_issuers)
        issuer = _one_non_empty_string(_decode_payload_pairs(encoded_jwt), "iss")
        return next(entry for entry in entries if entry.issuer == issuer)
    except (StopIteration, ValueError, TypeError, UnicodeError, binascii.Error, json.JSONDecodeError):
        raise _not_authorized(correlation_id) from None


def validate_access_token(
    encoded_jwt: str,
    allowed_issuers: AllowedTenantIssuerMap,
    verification_keys: Mapping[str, object],
    correlation_id: CorrelationId,
    *,
    canonical_tenant_claim_name: str = CANONICAL_TENANT_CLAIM,
    now: int | None = None,
) -> VerifiedApiIdentity:
    """Verify an access token before creating Sage API identity.

    The unverified issuer is used only for exact lookup in the fixed two-entry
    map. Signature verification and all identity checks then use that selected
    immutable configuration.
    """
    try:
        configuration = select_issuer_configuration(
            encoded_jwt, allowed_issuers, correlation_id
        )
        verification_key = verification_keys[configuration.issuer]
        jwt.decode(
            encoded_jwt,
            verification_key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            issuer=configuration.issuer,
            options={"require": ["iss"], "verify_aud": False, "verify_exp": False},
        )

        claims = _decode_payload_pairs(encoded_jwt)
        issuer = _one_non_empty_string(claims, "iss")
        expires_at = _one_integer(claims, "exp")
        client_id = _one_non_empty_string(claims, "client_id")
        token_use = _one_non_empty_string(claims, "token_use")
        scopes = frozenset(_one_non_empty_string(claims, "scope").split())
        subject = _one_non_empty_string(claims, "sub")
        tenant_id = _one_non_empty_string(claims, canonical_tenant_claim_name)
        current_time = int(time.time()) if now is None else now

        if (
            issuer != configuration.issuer
            or current_time >= expires_at
            or client_id not in configuration.trusted_client_ids
            or token_use != "access"
            or "sage-api/read" not in scopes
            or tenant_id != configuration.expected_tenant_id
        ):
            raise ValueError("token claims do not satisfy the selected issuer policy")
    except IdentityError:
        raise
    except (Exception,):
        raise _not_authorized(correlation_id) from None

    return VerifiedApiIdentity(
        issuer=issuer,
        subject=subject,
        tenant_id=tenant_id,
        client_id=client_id,
        scopes=scopes,
    )


def _validated_entries(
    allowed_issuers: AllowedTenantIssuerMap,
) -> tuple[ApiIssuerConfiguration, ApiIssuerConfiguration]:
    if type(allowed_issuers) is not AllowedTenantIssuerMap:
        raise ValueError("issuer map must be the immutable Sage identity map")
    entries = allowed_issuers.entries
    issuers = {entry.issuer for entry in entries}
    tenants = {entry.expected_tenant_id for entry in entries}
    if (
        len(entries) != 2
        or len(issuers) != 2
        or tenants != _REQUIRED_TENANTS
        or any(
            not entry.issuer.strip()
            or not entry.discovery_url.strip()
            or not entry.expected_tenant_id.strip()
            or not entry.trusted_client_ids
            for entry in entries
        )
    ):
        raise ValueError("issuer map must contain exactly two complete tenant entries")
    return entries  # type: ignore[return-value]


def _decode_payload_pairs(encoded_jwt: str) -> _JsonObject:
    if not isinstance(encoded_jwt, str):
        raise TypeError("access token must be a string")
    segments = encoded_jwt.split(".")
    if len(segments) != 3 or any(not segment for segment in segments):
        raise ValueError("access token must be a compact JWT")
    payload = segments[1].encode("ascii")
    decoded = base64.b64decode(
        payload + b"=" * (-len(payload) % 4), altchars=b"-_", validate=True
    )
    claims = json.loads(decoded, object_pairs_hook=_JsonObject)
    if not isinstance(claims, _JsonObject):
        raise ValueError("JWT payload must be an object")
    return claims


def _one_non_empty_string(claims: _JsonObject, name: str) -> str:
    values = [value for key, value in claims if key == name]
    if len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
        raise ValueError(f"claim {name!r} must occur once as a non-empty string")
    return values[0]


def _one_integer(claims: _JsonObject, name: str) -> int:
    values = [value for key, value in claims if key == name]
    if len(values) != 1 or isinstance(values[0], bool) or not isinstance(values[0], int):
        raise ValueError(f"claim {name!r} must occur once as an integer")
    return values[0]


def _not_authorized(correlation_id: CorrelationId) -> IdentityError:
    return IdentityError(IdentityErrorCode.NOT_AUTHORIZED, correlation_id)
