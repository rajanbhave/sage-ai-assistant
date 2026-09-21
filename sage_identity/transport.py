"""Authentication transport and non-observable sink primitives."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TypeAlias
from uuid import uuid4

AUTHORIZATION_HEADER = "Authorization"
CORRELATION_HEADER = "X-Sage-Correlation-Id"
REDACTED_AUTH_ARTIFACT = "[REDACTED_AUTH_ARTIFACT]"

_BEARER_PATTERN = re.compile(
    r"Bearer ([A-Za-z0-9\-._~+/]+={0,})", re.ASCII | re.IGNORECASE
)
_CORRELATION_PATTERN = re.compile(r"[0-9a-f]{32}", re.ASCII)
_OMIT = object()


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticationArtifact:
    """Immutable credential value whose provenance is limited to Authorization transport."""

    _value: str = field(repr=False)
    provenance: str = "authorization"

    def __post_init__(self) -> None:
        if not isinstance(self._value, str) or not self._value:
            raise ValueError("authentication artifacts must be non-empty strings")
        if self.provenance != "authorization":
            raise ValueError("only Authorization transport artifacts are accepted")

    def __repr__(self) -> str:
        return "AuthenticationArtifact([REDACTED])"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class CorrelationId:
    """Opaque, non-secret identifier created once for an invocation."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _CORRELATION_PATTERN.fullmatch(
            self.value
        ):
            raise ValueError("correlation ID must be 32 lowercase hexadecimal characters")

    @classmethod
    def new(cls) -> CorrelationId:
        """Create a new opaque invocation correlation ID."""
        return cls(uuid4().hex)


class IdentityErrorCode(str, Enum):
    """Stable public identity failure codes."""

    TOKEN_ISSUANCE_REJECTED = "token_issuance_rejected"
    LANE_INVALID = "lane_invalid"
    SESSION_REQUIRED = "session_required"
    SESSION_EXPIRED = "session_expired"
    IDENTITY_INVALID = "identity_invalid"
    TENANT_IDENTITY_INVALID = "tenant_identity_invalid"
    NOT_AUTHORIZED = "not_authorized"
    REQUEST_FAILED = "request_failed"


_IDENTITY_ERROR_MESSAGES = MappingProxyType(
    {
        IdentityErrorCode.TOKEN_ISSUANCE_REJECTED: "Token issuance was rejected.",
        IdentityErrorCode.LANE_INVALID: "The selected lane is invalid.",
        IdentityErrorCode.SESSION_REQUIRED: "Authentication is required.",
        IdentityErrorCode.SESSION_EXPIRED: "The session has expired.",
        IdentityErrorCode.IDENTITY_INVALID: "Authentication failed.",
        IdentityErrorCode.TENANT_IDENTITY_INVALID: "Tenant identity validation failed.",
        IdentityErrorCode.NOT_AUTHORIZED: "The request is not authorized.",
        IdentityErrorCode.REQUEST_FAILED: "The request failed.",
    }
)


@dataclass(frozen=True, slots=True)
class IdentityError(Exception):
    """Stable identity failure containing only public, non-secret fields."""

    code: IdentityErrorCode
    correlation_id: CorrelationId

    @property
    def message(self) -> str:
        """Return the fixed public message for this error code."""
        return _IDENTITY_ERROR_MESSAGES[self.code]

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationTransport:
    """The only serializer allowed to unwrap an authentication artifact."""

    _artifact: AuthenticationArtifact = field(repr=False)

    def __post_init__(self) -> None:
        _validate_bearer_value(self._artifact._value)

    def as_headers(self) -> dict[str, str]:
        """Build exactly one trusted Authorization header."""
        return {AUTHORIZATION_HEADER: f"Bearer {self._artifact._value}"}

    def __repr__(self) -> str:
        return "AuthorizationTransport([REDACTED])"


SafeScalar: TypeAlias = str | int | float | bool | None
SafeValue: TypeAlias = SafeScalar | list["SafeValue"] | dict[str, "SafeValue"]


def parse_bearer_authorization(
    header_values: str | Sequence[object] | None,
    correlation_id: CorrelationId,
) -> AuthenticationArtifact:
    """Parse exactly one strict Bearer header without changing bearer bytes."""
    if isinstance(header_values, str):
        values: Sequence[object] | None = (header_values,)
    elif isinstance(header_values, Sequence):
        values = header_values
    else:
        values = None
    if values is None or len(values) != 1 or not isinstance(values[0], str):
        raise IdentityError(IdentityErrorCode.IDENTITY_INVALID, correlation_id)

    match = _BEARER_PATTERN.fullmatch(values[0])
    if match is None:
        raise IdentityError(IdentityErrorCode.IDENTITY_INVALID, correlation_id)

    return AuthenticationArtifact(match.group(1))


def build_authorization_transport(
    artifact: AuthenticationArtifact,
) -> AuthorizationTransport:
    """Place an artifact into the sole trusted unwrapping boundary."""
    return AuthorizationTransport(artifact)


def build_correlation_headers(correlation_id: CorrelationId) -> dict[str, str]:
    """Build the non-secret correlation transport header."""
    return {CORRELATION_HEADER: correlation_id.value}


def serialize_safe_fields(fields: Mapping[str, object]) -> dict[str, SafeValue]:
    """Serialize application fields while omitting authentication artifacts."""
    return _serialize_fields(fields, redact=False)


def serialize_log_fields(fields: Mapping[str, object]) -> dict[str, SafeValue]:
    """Serialize explicitly selected log fields with complete redaction."""
    return _serialize_fields(fields, redact=True)


def serialize_identity_error(error: IdentityError) -> dict[str, SafeValue]:
    """Serialize an identity failure using only its stable safe fields."""
    return serialize_safe_fields(
        {
            "code": error.code.value,
            "message": error.message,
            "correlation_id": error.correlation_id,
        }
    )


def _validate_bearer_value(value: str) -> None:
    if not isinstance(value, str) or _BEARER_PATTERN.fullmatch(f"Bearer {value}") is None:
        raise ValueError("bearer cannot be represented as strict Authorization transport")


def _serialize_fields(
    fields: Mapping[str, object], *, redact: bool
) -> dict[str, SafeValue]:
    serialized = _sanitize_value(fields, redact=redact)
    if not isinstance(serialized, dict):
        raise TypeError("safe fields must serialize to an object")
    return serialized


def _sanitize_value(value: object, *, redact: bool) -> SafeValue | object:
    if isinstance(value, AuthenticationArtifact):
        return REDACTED_AUTH_ARTIFACT if redact else _OMIT
    if isinstance(value, CorrelationId):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, SafeValue] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("safe field names must be strings")
            sanitized = _sanitize_value(nested, redact=redact)
            if sanitized is not _OMIT:
                result[key] = sanitized  # type: ignore[assignment]
        return result
    if isinstance(value, (list, tuple)):
        result_list: list[SafeValue] = []
        for nested in value:
            sanitized = _sanitize_value(nested, redact=redact)
            if sanitized is not _OMIT:
                result_list.append(sanitized)  # type: ignore[arg-type]
        return result_list
    raise TypeError(f"unsupported safe field value type: {type(value).__name__}")
