import json
import logging

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from sage_identity import (
    AllowedTenantIssuerMap,
    ApiIssuerConfiguration,
    AuthenticationArtifact,
    CorrelationId,
    IdentityError,
    serialize_identity_error,
    serialize_log_fields,
    serialize_safe_fields,
    parse_bearer_authorization,
)
from sage_api import create_application


def api():
    private_a = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://issuer.example/tenant-a"
    issuer_map = AllowedTenantIssuerMap((ApiIssuerConfiguration(
        issuer, issuer + "/.well-known", "Tenant_A", frozenset({"client-a"}),
    ), ApiIssuerConfiguration(
        "https://issuer.example/tenant-b", "https://issuer.example/tenant-b/.well-known", "Tenant_B", frozenset({"client-b"}),
    )))
    return private_a, issuer_map, create_application(issuer_map, {issuer: private_a.public_key(), "https://issuer.example/tenant-b": private_a.public_key()}, frozenset({"mcp-a", "mcp-b"}))


def token(key, lane="a", **overrides):
    issuer, client_id, tenant_id, subject = {
        "a": ("https://issuer.example/tenant-a", "client-a", "Tenant_A", "subject-a"),
        "b": ("https://issuer.example/tenant-b", "client-b", "Tenant_B", "subject-b"),
    }[lane]
    claims = {
        "iss": issuer, "exp": 4_000_000_000, "client_id": client_id, "token_use": "access",
        "scope": "sage-api/read", "sub": subject, "custom:tenant_id": tenant_id,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


def call(
    app,
    path="/products",
    query="product_type=motor",
    source="mcp-a",
    authorization=None,
    *,
    trusted_source=True,
):
    result = {}
    def start(status, headers):
        result["status"] = status
    environ = {
        "REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": query,
        "REMOTE_ADDR": source, "HTTP_X_SAGE_CORRELATION_ID": "a" * 32,
        "HTTP_AUTHORIZATION": authorization,
    }
    if trusted_source:
        environ["sage.source_path"] = source
    body = app(environ, start)
    result["body"] = json.loads(b"".join(body))
    return result


def test_transport_is_strict_and_sinks_are_safe():
    correlation = CorrelationId("a" * 32)
    artifact = parse_bearer_authorization("Bearer abc.DEF~1", correlation)
    assert artifact._value == "abc.DEF~1"
    assert serialize_safe_fields({"token": artifact, "correlation_id": correlation}) == {"correlation_id": "a" * 32}
    assert serialize_log_fields({"token": artifact})["token"] == "[REDACTED_AUTH_ARTIFACT]"
    assert serialize_identity_error(IdentityError(__import__("sage_identity").IdentityErrorCode.REQUEST_FAILED, correlation))["message"] == "The request failed."


def test_sage_api_http_boundary_validates_and_isolates_reads():
    private, _, app = api()
    tenant_a_token = f"Bearer {token(private, 'a')}"
    tenant_b_token = f"Bearer {token(private, 'b')}"
    tenant_a = call(app, authorization=tenant_a_token)
    tenant_b = call(app, source="mcp-b", authorization=tenant_b_token)
    assert tenant_a["status"] == tenant_b["status"] == "200 OK"
    assert [product["product_id"] for product in tenant_a["body"]["products"]] == ["AXA-MOT-001"]
    assert [product["product_id"] for product in tenant_b["body"]["products"]] == ["ALZ-MOT-001"]
    assert tenant_a["body"]["products"][0]["name"] == "AXA Drive Protect"
    assert tenant_b["body"]["products"][0]["name"] == "Allianz AutoGuard Plus"

    tenant_a_shared = call(app, path="/claims", query="claim_reference=CLM-12345", authorization=tenant_a_token)
    tenant_b_shared = call(app, path="/claims", query="claim_reference=CLM-12345", source="mcp-b", authorization=tenant_b_token)
    assert tenant_a_shared["body"]["claim"]["amount"] == 3200.0
    assert tenant_b_shared["body"]["claim"]["amount"] == 9700.0

    assert call(app, path="/claims", query="claim_reference=CLM-5454", authorization=tenant_a_token)["body"]["claim"] is None
    assert call(app, path="/claims", query="claim_reference=CLM-12346", source="mcp-b", authorization=tenant_b_token)["body"]["claim"] is None
    assert call(app, source="mcp-b", authorization=f"Bearer {token(private, 'b', exp=0)}")["status"] == "403 Forbidden"

    denied = call(app, source="not-approved", authorization=f"Bearer {token(private)}")
    assert denied["status"] == "403 Forbidden"

    address_only = call(
        app,
        source="mcp-a",
        authorization=tenant_a_token,
        trusted_source=False,
    )
    assert address_only["status"] == "403 Forbidden"

    malformed = call(app, authorization="Bearer not-a-jwt")
    assert malformed["status"] == "403 Forbidden"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://issuer.example/unknown"},
        {"client_id": "wrong-client"},
        {"exp": 0},
        {"scope": "sage-mcp/invoke"},
        {"sub": ""},
        {"custom:tenant_id": "Tenant_B"},
    ],
    ids=("issuer", "client", "expiry", "scope", "subject", "tenant"),
)
def test_sage_api_independently_rejects_invalid_identity_controls(overrides):
    private, _, app = api()

    response = call(app, authorization=f"Bearer {token(private, **overrides)}")

    assert response["status"] == "403 Forbidden"
    assert response["body"]["code"] == "not_authorized"


def test_sage_api_independently_rejects_wrong_signature():
    _, _, app = api()
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    response = call(app, authorization=f"Bearer {token(other_key)}")

    assert response["status"] == "403 Forbidden"
    assert response["body"]["code"] == "not_authorized"



def test_sage_api_verifies_tokens_signed_by_any_published_pool_key():
    """A Cognito pool publishes several signing keys and uses any of them."""
    first = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    second = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer_a = "https://issuer.example/tenant-a"
    issuer_b = "https://issuer.example/tenant-b"
    issuer_map = AllowedTenantIssuerMap((
        ApiIssuerConfiguration(issuer_a, issuer_a + "/.well-known", "Tenant_A", frozenset({"client-a"})),
        ApiIssuerConfiguration(issuer_b, issuer_b + "/.well-known", "Tenant_B", frozenset({"client-b"})),
    ))
    keys = {
        issuer_a: {"kid-1": first.public_key(), "kid-2": second.public_key()},
        issuer_b: {"kid-1": first.public_key()},
    }
    app = create_application(issuer_map, keys, frozenset({"mcp-a"}))

    for key, kid in ((first, "kid-1"), (second, "kid-2")):
        signed = jwt.encode(
            {
                "iss": issuer_a, "exp": 4_000_000_000, "client_id": "client-a",
                "token_use": "access", "scope": "sage-api/read", "sub": "subject-a",
                "custom:tenant_id": "Tenant_A",
            },
            key,
            algorithm="RS256",
            headers={"kid": kid},
        )
        assert call(app, authorization=f"Bearer {signed}")["status"] == "200 OK"

    unknown_kid = jwt.encode(
        {
            "iss": issuer_a, "exp": 4_000_000_000, "client_id": "client-a",
            "token_use": "access", "scope": "sage-api/read", "sub": "subject-a",
            "custom:tenant_id": "Tenant_A",
        },
        first,
        algorithm="RS256",
        headers={"kid": "rotated-away"},
    )
    assert call(app, authorization=f"Bearer {unknown_kid}")["status"] == "403 Forbidden"


def test_jwks_configuration_builds_a_key_per_identifier():
    from sage_api.http import _keys_by_id

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private.public_key().public_numbers()

    def b64(value: int, length: int) -> str:
        import base64
        return base64.urlsafe_b64encode(
            value.to_bytes(length, "big")
        ).rstrip(b"=").decode()

    jwks = {
        "keys": [
            {
                "kty": "RSA", "alg": "RS256", "use": "sig", "kid": "kid-1",
                "n": b64(public_numbers.n, 256), "e": b64(public_numbers.e, 3),
            }
        ]
    }

    assert list(_keys_by_id(jwks)) == ["kid-1"]
    with pytest.raises(ValueError):
        _keys_by_id({"keys": []})
    with pytest.raises(ValueError):
        _keys_by_id({"keys": [{"kty": "RSA"}]})



def test_audit_event_reaches_the_log_with_no_credential(caplog):
    """The audit event is the only authorization evidence, so it must be emitted.

    Lambda leaves the root logger at WARNING and its formatter discards unknown
    record attributes, so an INFO record carrying fields in ``extra`` never
    reached CloudWatch. These assertions pin the fields into the message itself.
    """
    private, _issuers, app = api()
    raw = token(private, "a")

    with caplog.at_level(logging.INFO, logger="sage_api.http"):
        assert call(app, authorization=f"Bearer {raw}")["status"] == "200 OK"

    authorized = [r for r in caplog.records if r.levelno == logging.INFO]
    assert authorized, "no INFO audit record was emitted"
    rendered = authorized[-1].getMessage()
    payload = json.loads(rendered.split(" ", 3)[3])
    assert payload == {
        "correlation_id": "a" * 32,
        "outcome": "authorized",
        "subject": "subject-a",
        "tenant_id": "Tenant_A",
    }
    # The bearer must never be recoverable from the audit trail.
    assert raw not in rendered
    for segment in raw.split("."):
        assert segment not in rendered


def test_audit_failure_event_records_only_a_stable_code(caplog):
    private, _issuers, app = api()

    with caplog.at_level(logging.INFO, logger="sage_api.http"):
        denied = call(app, source="not-approved", authorization=f"Bearer {token(private)}")

    assert denied["status"] == "403 Forbidden"
    failures = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert failures, "no failure audit record was emitted"
    payload = json.loads(failures[-1].getMessage().split(" ", 4)[4])
    assert set(payload) == {"correlation_id", "outcome"}
    assert "subject" not in payload and "tenant_id" not in payload
