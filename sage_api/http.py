"""Small stdlib WSGI boundary for Sage tenant data."""

from __future__ import annotations

import copy
import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

import jwt

from sage_identity import (
    AllowedTenantIssuerMap,
    ApiIssuerConfiguration,
    CorrelationId,
    IdentityError,
    IdentityErrorCode,
    serialize_identity_error,
    parse_bearer_authorization,
    serialize_log_fields,
)

from .identity import VerifiedApiIdentity, validate_access_token
from .mock_data import MOCK_DATA

logger = logging.getLogger(__name__)
# The audit event is the Sage API's only evidence that a request was authorized,
# so it must reach CloudWatch. Lambda leaves the root logger at WARNING, which
# would silently drop every INFO audit record.
logger.setLevel(logging.INFO)


def _audit_payload(fields: Mapping[str, object]) -> str:
    """Render one audit event as a compact, greppable, credential-free string.

    The fields are placed in the log message itself rather than in ``extra``
    because Lambda's default formatter discards unknown record attributes, which
    would strip the correlation ID, subject, tenant, and outcome an auditor needs.
    ``serialize_log_fields`` redacts authentication artifacts, so no bearer value
    can reach the log.
    """
    return json.dumps(
        serialize_log_fields(fields), sort_keys=True, separators=(",", ":")
    )


def _keys_by_id(jwks: object) -> dict[str, object]:
    """Build a key-identifier map from one issuer's published JWKS.

    Cognito serves the pool's public signing keys at its JWKS endpoint, so
    deployment configuration carries that document unchanged and no private or
    secret material is involved.
    """
    keys = jwks.get("keys") if isinstance(jwks, Mapping) else jwks
    if not isinstance(keys, list) or not keys:
        raise ValueError("Sage API issuer keys must be a non-empty JWKS")

    selected: dict[str, object] = {}
    for key in keys:
        if not isinstance(key, Mapping) or not isinstance(key.get("kid"), str):
            raise ValueError("each JWKS entry requires a string key identifier")
        selected[str(key["kid"])] = jwt.algorithms.RSAAlgorithm.from_jwk(
            json.dumps(dict(key))
        )
    return selected


@dataclass(frozen=True, slots=True)
class SageApiApplication:
    """HTTP application that owns validation, authorization, and demo data."""

    issuers: AllowedTenantIssuerMap
    verification_keys: Mapping[str, object]
    approved_source_paths: frozenset[str]

    def __post_init__(self) -> None:
        if len(self.issuers) != 2 or set(self.issuers) != set(self.verification_keys):
            raise ValueError("Sage API requires exactly two issuer keys")
        if not self.approved_source_paths or any(
            not isinstance(path, str) or not path.strip()
            for path in self.approved_source_paths
        ):
            raise ValueError("Sage API requires approved source paths")

    def __call__(self, environ: Mapping[str, object], start_response: Callable) -> list[bytes]:
        correlation = self._correlation(environ)
        try:
            if correlation is None:
                raise IdentityError(IdentityErrorCode.IDENTITY_INVALID, CorrelationId.new())
            self._check_source(environ, correlation)
            if environ.get("REQUEST_METHOD") != "GET":
                raise IdentityError(IdentityErrorCode.NOT_AUTHORIZED, correlation)
            token = self._authorization(environ, correlation)
            identity = validate_access_token(
                token,
                self.issuers,
                self.verification_keys,
                correlation,
            )
            payload = self._read(environ, identity, correlation)
            self._audit(identity, correlation, "authorized")
            return self._response(start_response, "200 OK", payload)
        except IdentityError as error:
            self._audit_error(error)
            return self._response(
                start_response,
                "401 Unauthorized" if error.code is not IdentityErrorCode.NOT_AUTHORIZED else "403 Forbidden",
                serialize_identity_error(error),
            )
        except (KeyError, TypeError, ValueError):
            error = IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation or CorrelationId.new())
            self._audit_error(error)
            return self._response(start_response, "400 Bad Request", serialize_identity_error(error))
        except Exception:
            error = IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation or CorrelationId.new())
            self._audit_error(error)
            return self._response(start_response, "500 Internal Server Error", serialize_identity_error(error))

    @classmethod
    def from_environment(cls) -> SageApiApplication:
        """Build the deployment-owned application from non-secret configuration."""
        raw_issuers = json.loads(os.environ.get("SAGE_API_ISSUER_MAP", "{}"))
        raw_keys = json.loads(os.environ.get("SAGE_API_PUBLIC_KEYS", "{}"))
        if not isinstance(raw_issuers, list) or not isinstance(raw_keys, dict):
            raise ValueError("Sage API issuer and key configuration is invalid")
        issuers = AllowedTenantIssuerMap(
            tuple(ApiIssuerConfiguration(**entry) for entry in raw_issuers)
        )
        return cls(
            issuers,
            {issuer: _keys_by_id(jwks) for issuer, jwks in raw_keys.items()},
            frozenset(
                path.strip()
                for path in os.environ.get("SAGE_API_APPROVED_SOURCES", "").split(",")
                if path.strip()
            ),
        )

    def _correlation(self, environ: Mapping[str, object]) -> CorrelationId | None:
        value = environ.get("HTTP_X_SAGE_CORRELATION_ID")
        if not isinstance(value, str):
            return None
        try:
            return CorrelationId(value)
        except ValueError:
            return None

    def _check_source(self, environ: Mapping[str, object], correlation: CorrelationId) -> None:
        source = environ.get("sage.source_path")
        if not isinstance(source, str) or source not in self.approved_source_paths:
            raise IdentityError(IdentityErrorCode.NOT_AUTHORIZED, correlation)

    def _authorization(self, environ: Mapping[str, object], correlation: CorrelationId) -> str:
        value = environ.get("HTTP_AUTHORIZATION")
        if not isinstance(value, str):
            raise IdentityError(IdentityErrorCode.NOT_AUTHORIZED, correlation)
        return parse_bearer_authorization(value, correlation)._value


    def _read(
        self,
        environ: Mapping[str, object],
        identity: VerifiedApiIdentity,
        correlation: CorrelationId,
    ) -> dict[str, object]:
        if not identity.subject or identity.tenant_id not in MOCK_DATA:
            raise IdentityError(IdentityErrorCode.NOT_AUTHORIZED, correlation)
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        path = str(environ.get("PATH_INFO", "")).rstrip("/")
        if path.endswith("/products"):
            product_type = self._one_query(query, "product_type", correlation)
            rows = [
                copy.deepcopy(product)
                for product in MOCK_DATA[identity.tenant_id]["products"]
                if product.get("type") == product_type
            ]
            return {"products": rows}
        if path.endswith("/claims"):
            reference = self._one_query(query, "claim_reference", correlation)
            claim = next(
                (
                    copy.deepcopy(item)
                    for item in MOCK_DATA[identity.tenant_id]["claims"]
                    if item.get("claim_reference") == reference
                ),
                None,
            )
            return {"claim": claim}
        raise IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation)

    @staticmethod
    def _one_query(query: Mapping[str, list[str]], name: str, correlation: CorrelationId) -> str:
        values = query.get(name, [])
        if len(values) != 1 or not values[0].strip():
            raise IdentityError(IdentityErrorCode.REQUEST_FAILED, correlation)
        return values[0]

    @staticmethod
    def _response(start_response: Callable, status: str, payload: Mapping[str, object]) -> list[bytes]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        start_response(status, [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
        return [body]

    @staticmethod
    def _audit(identity: VerifiedApiIdentity, correlation: CorrelationId, outcome: str) -> None:
        logger.info("Sage API request %s", _audit_payload({"correlation_id": correlation, "subject": identity.subject, "tenant_id": identity.tenant_id, "outcome": outcome}))

    @staticmethod
    def _audit_error(error: IdentityError) -> None:
        logger.warning("Sage API request failed %s", _audit_payload({"correlation_id": error.correlation_id, "outcome": error.code.value}))


def create_application(
    issuers: AllowedTenantIssuerMap,
    verification_keys: Mapping[str, object],
    approved_source_paths: frozenset[str],
) -> SageApiApplication:
    """Create the one deployed Sage API boundary for tests and local serving."""
    return SageApiApplication(issuers, verification_keys, approved_source_paths)


_application: SageApiApplication | None = None

def application(environ: Mapping[str, object], start_response: Callable) -> list[bytes]:
    """WSGI entrypoint; configuration is loaded once from deployment state."""
    global _application
    if _application is None:
        try:
            _application = SageApiApplication.from_environment()
        except Exception:
            # Deployment configuration is invalid. Fail closed with a safe body
            # rather than letting the construction error escape the caller.
            logger.exception("Sage API configuration is invalid")
            error = IdentityError(
                IdentityErrorCode.REQUEST_FAILED, CorrelationId.new()
            )
            payload = json.dumps(
                serialize_identity_error(error), separators=(",", ":")
            ).encode("utf-8")
            start_response(
                "500 Internal Server Error",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(payload))),
                ],
            )
            return [payload]
    return _application(environ, start_response)


def main() -> None:
    """Serve Sage API over the stdlib WSGI server."""
    host = os.environ.get("SAGE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SAGE_API_PORT", "8081"))
    with make_server(host, port, application) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
