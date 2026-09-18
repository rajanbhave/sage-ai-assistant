import base64
import json
import logging

import pytest
from fastmcp.exceptions import ToolError

import mcp_server.tools.data_tools as data_tools
from mcp_server.identity import McpIdentityConfiguration, establish_request_identity
from mcp_server.sage_api_client import SageApiRequestError
from sage_identity import AuthenticationArtifact, CorrelationId, IdentityError


def bearer(**claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"Bearer e30.{payload}.sig"


def config():
    return McpIdentityConfiguration("Tenant_A", "Tenant_A", "custom:tenant_id")


def test_mcp_identity_extracts_managed_validated_subject_and_binds_hosting_lane():
    token = bearer(
        iss="not-reverified-by-the-application",
        sub="user",
        **{"custom:tenant_id": "Tenant_A"},
        token_use="not-reverified-by-the-application",
        scope="not-reverified-by-the-application",
    )
    artifact = AuthenticationArtifact(token.removeprefix("Bearer "))
    identity = establish_request_identity(artifact, config(), CorrelationId("a" * 32))
    assert (identity.lane_id, identity.subject, identity.tenant_id) == ("Tenant_A", "user", "Tenant_A")
    assert not hasattr(identity, "issuer")


def test_mcp_identity_fails_closed_for_malformed_or_cross_lane_claims():
    correlation = CorrelationId("a" * 32)
    wrong_lane = bearer(sub="user", **{"custom:tenant_id": "Tenant_B"})
    with pytest.raises(IdentityError):
        establish_request_identity(
            AuthenticationArtifact(wrong_lane.removeprefix("Bearer ")),
            config(),
            correlation,
        )

    duplicate_tenant_payload = base64.urlsafe_b64encode(
        b'{"sub":"user","custom:tenant_id":"Tenant_A","custom:tenant_id":"Tenant_A"}'
    ).rstrip(b"=").decode()
    with pytest.raises(IdentityError):
        establish_request_identity(
            AuthenticationArtifact(f"e30.{duplicate_tenant_payload}.sig"),
            config(),
            correlation,
        )


def test_data_tool_failures_are_stable_and_redacted(caplog):
    caplog.set_level(logging.WARNING, logger="mcp_server.tools.data_tools")
    correlation = CorrelationId("b" * 32)

    with pytest.raises(ToolError) as api_failure:
        data_tools._call_sage_api(
            lambda: (_ for _ in ()).throw(SageApiRequestError()),
            "products",
            correlation,
        )
    assert json.loads(str(api_failure.value)) == {
        "code": "request_failed",
        "message": "The request failed.",
        "correlation_id": "b" * 32,
    }

    sentinel_bearer = "sentinel-bearer"
    with pytest.raises(ToolError) as identity_failure:
        data_tools._get_request(
            {
                "Authorization": f"Bearer {sentinel_bearer}",
                "X-Sage-Correlation-Id": correlation.value,
            }
        )
    assert json.loads(str(identity_failure.value))["code"] == "tenant_identity_invalid"
    assert sentinel_bearer not in caplog.text
    assert caplog.records[0].identity_error == {
        "code": "request_failed",
        "correlation_id": correlation.value,
    }
