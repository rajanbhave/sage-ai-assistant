import json

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
