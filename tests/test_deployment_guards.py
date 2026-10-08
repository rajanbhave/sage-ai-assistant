import json

import pytest

from scripts.deploy_pre_token_lambda import (
    build_customizer_config,
    require_qualified_lambda_arn,
)

ACCOUNT = "arn:aws:lambda:us-east-1:111122223333:function:sage-pre-token-tenant-a"


@pytest.mark.parametrize(
    "arn",
    [
        ACCOUNT,  # unqualified: the defect the weak guard let through
        f"{ACCOUNT}:$LATEST",
        "arn:aws:lambda:us-east-1:111122223333:sage-pre-token-tenant-a:1",
        "not-an-arn",
        "",
    ],
)
def test_unqualified_or_mutable_lambda_arns_are_rejected(arn):
    with pytest.raises(ValueError):
        require_qualified_lambda_arn(arn)


@pytest.mark.parametrize("qualifier", ["1", "tenant-a"])
def test_qualified_version_and_alias_arns_are_accepted(qualifier):
    arn = f"{ACCOUNT}:{qualifier}"
    assert require_qualified_lambda_arn(arn) == arn


def test_customizer_config_binds_one_lane_and_only_sage_scopes():
    serialized = build_customizer_config(
        lane_id="Tenant_A",
        user_pool_id="us-east-1_pool",
        client_ids=["client-a"],
        subjects=["subject-a"],
        assignment_attribute="custom:tenant_assignment",
        scopes=["sage-agent/invoke", "sage-api/read"],
    )
    config = json.loads(serialized)

    assert config["expectedTenant"] == "Tenant_A"
    assert config["canonicalTenantClaimName"] == "custom:tenant_id"
    assert config["trustedClientIds"] == ["client-a"]
    assert config["scopeGrants"] == [
        {
            "clientId": "client-a",
            "scopes": ["sage-agent/invoke", "sage-api/read"],
            "subject": "subject-a",
        }
    ]

    with pytest.raises(ValueError):
        build_customizer_config(
            lane_id="Tenant_A",
            user_pool_id="us-east-1_pool",
            client_ids=["client-a"],
            subjects=["subject-a"],
            assignment_attribute="custom:tenant_assignment",
            scopes=["admin/root"],
        )

    with pytest.raises(ValueError):
        build_customizer_config(
            lane_id="Tenant_A",
            user_pool_id="us-east-1_pool",
            client_ids=[],
            subjects=["subject-a"],
            assignment_attribute="custom:tenant_assignment",
            scopes=["sage-api/read"],
        )


def test_sage_api_fails_closed_when_configuration_is_invalid(monkeypatch):
    import sage_api.http as http_module

    monkeypatch.setattr(http_module, "_application", None)
    monkeypatch.setenv("SAGE_API_ISSUER_MAP", "{not json")
    captured: dict = {}

    def start(status, headers):
        captured["status"] = status

    body = http_module.application({"REQUEST_METHOD": "GET"}, start)

    assert captured["status"] == "500 Internal Server Error"
    assert json.loads(b"".join(body).decode())["code"] == "request_failed"
