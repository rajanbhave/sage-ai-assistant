"""The negative-path validator checks and their fixture gating."""

import base64
import json

import pytest

from scripts import validate_route_c
from scripts.deploy_user_pool import (
    load_resource_server_pool_ids,
    render_resource_servers,
)
from scripts.provision_validation_fixtures import canary_scopes, plan
from scripts.validate_route_c import (
    DOOR_SCOPE,
    Recorder,
    check_scope_canaries,
    check_unapproved_client,
    door_urls,
)
from tests.env import lane_topology, topology

REGION = topology("SAGE_TEST_REGION")
LANE = {"Tenant_A": lane_topology("Tenant_A")}


def checks(rec: Recorder) -> list[dict]:
    return rec.report({})["checks"]


def statuses(rec: Recorder) -> list[str]:
    return [check["status"] for check in checks(rec)]


def fake_token(scopes: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"scope": scopes}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_absent_fixtures_skip_instead_of_passing():
    """A missing fixture must never look like a satisfied negative check."""
    rec = Recorder()

    check_unapproved_client(rec, LANE, {}, REGION, "corr", skip_agent=True)
    check_scope_canaries(rec, LANE, {}, REGION, "corr", skip_agent=True)

    assert statuses(rec) == ["SKIP", "SKIP"]
    assert all("fixture" in check["observed"] for check in checks(rec))


def test_a_canary_that_still_holds_its_door_scope_fails_loudly(monkeypatch):
    """The canary is only evidence if its grant really omits the door scope."""
    monkeypatch.setattr(
        validate_route_c,
        "authenticate_user",
        lambda _client, _user: fake_token("sage-gateway/invoke sage-api/read"),
    )
    monkeypatch.setattr(
        validate_route_c,
        "post_json",
        lambda *_args, **_kwargs: pytest.fail("must not reach the door"),
    )
    rec = Recorder()
    fixtures = {
        "Tenant_A": {
            "canaryUsers": {"gateway": {"username": "u", "password": "p"}}
        }
    }

    check_scope_canaries(rec, LANE, fixtures, REGION, "corr", skip_agent=True)

    gateway = [c for c in checks(rec) if "canary token omits" in c["name"]]
    assert [c["status"] for c in gateway] == ["FAIL"]
    assert "not restricted" in gateway[0]["observed"]


def test_a_restricted_canary_asserts_the_door_rejects_it(monkeypatch):
    monkeypatch.setattr(
        validate_route_c,
        "authenticate_user",
        lambda _client, _user: fake_token("sage-api/read"),
    )
    monkeypatch.setattr(
        validate_route_c, "post_json", lambda *_args, **_kwargs: (403, "")
    )
    rec = Recorder()
    fixtures = {
        "Tenant_A": {
            "canaryUsers": {"gateway": {"username": "u", "password": "p"}}
        }
    }

    check_scope_canaries(rec, LANE, fixtures, REGION, "corr", skip_agent=True)

    gateway = [
        c
        for c in checks(rec)
        if c["name"] == "gateway rejects a token missing only its own scope"
    ]
    assert [c["status"] for c in gateway] == ["PASS"]


def test_door_urls_and_scopes_agree_on_door_names():
    urls = door_urls(LANE["Tenant_A"], REGION, skip_agent=False)

    assert set(urls) == {"agent_runtime", "gateway", "mcp_runtime"}
    for door in urls:
        assert DOOR_SCOPE[door].endswith("/invoke")


def test_canary_scopes_omit_exactly_one_door_scope():
    for door in ("agent_runtime", "gateway", "mcp_runtime"):
        scopes = canary_scopes(door)
        assert DOOR_SCOPE[door] not in scopes
        assert len(scopes) == 3


def test_fixture_plan_issues_no_aws_calls_and_names_the_unapproved_client():
    manifest = {"region": REGION, "lanes": [dict(LANE["Tenant_A"])]}

    described = plan(manifest)

    assert described["awsMutationCallsIssued"] == 0
    lane = described["lanes"][0]
    assert lane["unapprovedClientName"].endswith("unapproved-client")
    assert "allowedClients" in lane["unapprovedClientNote"]
    assert len(lane["canaryUsers"]) == 3


def test_resource_servers_render_without_an_agent_runtime_endpoint():
    """The scopes must be creatable before any Agent Runtime exists."""
    pools = load_resource_server_pool_ids(
        {"TENANT_A_USER_POOL_ID": "pool-a", "TENANT_B_USER_POOL_ID": "pool-b"}
    )
    described = render_resource_servers(pools)

    assert described["awsMutationCallsIssued"] == 0
    assert described["scopes"] == [
        "sage-agent/invoke",
        "sage-gateway/invoke",
        "sage-mcp/invoke",
        "sage-api/read",
        "sage-api/write",
    ]


def test_resource_server_pools_must_be_distinct():
    with pytest.raises(ValueError):
        load_resource_server_pool_ids(
            {"TENANT_A_USER_POOL_ID": "same", "TENANT_B_USER_POOL_ID": "same"}
        )
