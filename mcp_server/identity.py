"""Lane-bound identity validation for Runtime-authorized MCP requests."""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

from sage_identity import (
    AuthenticationArtifact,
    TENANT_A,
    TENANT_B,
    CorrelationId,
    IdentityError,
    IdentityErrorCode,
)

_REQUIRED_TENANTS = frozenset({TENANT_A, TENANT_B})


class _JsonObject(tuple[tuple[str, object], ...]):
    """JSON object represented as ordered pairs so duplicate keys survive."""


@dataclass(frozen=True, slots=True)
class McpIdentityConfiguration:
    """Trusted application binding for one managed-authorized hosting lane."""

    lane_id: str
    expected_tenant_id: str
    canonical_tenant_claim_name: str

    def __post_init__(self) -> None:
        required = (
            self.lane_id,
            self.expected_tenant_id,
            self.canonical_tenant_claim_name,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            raise ValueError("MCP identity configuration values must be non-empty strings")
        if self.lane_id != self.expected_tenant_id:
            raise ValueError("MCP lane and expected tenant must match")
        if self.lane_id not in _REQUIRED_TENANTS:
            raise ValueError("MCP lane must be Tenant_A or Tenant_B")

    @classmethod
    def from_environment(cls) -> McpIdentityConfiguration:
        """Load the hosting lane binding from deployment-owned environment values."""
        return cls(
            lane_id=os.environ.get("SAGE_LANE_ID", ""),
            expected_tenant_id=os.environ.get("SAGE_EXPECTED_TENANT", ""),
            canonical_tenant_claim_name=os.environ.get(
                "SAGE_CANONICAL_TENANT_CLAIM", ""
            ),
        )


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    """Application identity extracted after managed Runtime validation."""

    lane_id: str
    subject: str
    tenant_id: str


def establish_request_identity(
    bearer: AuthenticationArtifact,
    configuration: McpIdentityConfiguration,
    correlation_id: CorrelationId,
) -> RequestIdentity:
    """Extract subject and tenant context already validated by AgentCore.

    Cryptographic validity, expiry, issuer, client, token type, and managed scope
    are enforced by the hosting MCP Runtime custom JWT authorizer. Application
    code only parses the forwarded claims needed for same-lane business binding.
    """
    try:
        claims = _decode_payload_pairs(bearer._value)
        subject = _one_non_empty_string(claims, "sub")
        tenant_id = _one_non_empty_string(
            claims, configuration.canonical_tenant_claim_name
        )
    except (ValueError, TypeError, UnicodeError, binascii.Error, json.JSONDecodeError):
        raise _identity_error(correlation_id) from None

    if tenant_id != configuration.expected_tenant_id:
        raise _identity_error(correlation_id)

    return RequestIdentity(
        lane_id=configuration.lane_id,
        subject=subject,
        tenant_id=tenant_id,
    )


def header_values(headers: Mapping[str, object], name: str) -> tuple[object, ...]:
    """Return every case-insensitive occurrence of a request header."""
    return _header_values(headers, name.lower())


def _header_values(headers: Mapping[str, object], name: str) -> tuple[object, ...]:
    values: list[object] = []
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name:
            if isinstance(value, (list, tuple)):
                values.extend(value)
            else:
                values.append(value)
    return tuple(values)


def _decode_payload_pairs(encoded_jwt: str) -> _JsonObject:
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
    if (
        len(values) != 1
        or not isinstance(values[0], str)
        or not values[0].strip()
    ):
        raise ValueError(f"claim {name!r} must occur once as a non-empty string")
    return values[0]


def _identity_error(correlation_id: CorrelationId) -> IdentityError:
    return IdentityError(IdentityErrorCode.TENANT_IDENTITY_INVALID, correlation_id)
