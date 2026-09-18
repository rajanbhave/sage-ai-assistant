from datetime import date

import pytest

from sage_identity import (
    HTTP_MCP_PASSTHROUGH_DOCUMENTATION_URL,
    JWT_PASSTHROUGH_DOCUMENTATION_URL,
    TENANT_A,
    TENANT_B,
    TargetCapabilityEvidence,
    verify_target_capability_evidence,
)


def test_target_capability_verification_requires_one_of_both_fixed_lanes():
    for lane_id in (TENANT_A, TENANT_B):
        evidence = TargetCapabilityEvidence(
            lane_id,
            "http_passthrough",
            HTTP_MCP_PASSTHROUGH_DOCUMENTATION_URL,
            date.today(),
            "MCP",
            "JWT_PASSTHROUGH",
            "https://mcp.example/invoke",
            JWT_PASSTHROUGH_DOCUMENTATION_URL,
            "{}",
            "https://mcp.example/invoke",
            True,
        )
        assert verify_target_capability_evidence(evidence) is evidence

    with pytest.raises(ValueError):
        verify_target_capability_evidence(
            TargetCapabilityEvidence(
                "Tenant_C",
                "http_passthrough",
                HTTP_MCP_PASSTHROUGH_DOCUMENTATION_URL,
                date.today(),
                "MCP",
                "JWT_PASSTHROUGH",
                "https://mcp.example/invoke",
            )
        )


def test_dry_run_selects_only_the_failed_lane_for_rollback(monkeypatch):
    from pathlib import Path
    from scripts import plan_identity_deployment as deployment_plan

    rollback_digests = {TENANT_A: "digest-a", TENANT_B: "digest-b"}
    monkeypatch.setattr(
        deployment_plan,
        "validate_deployment_manifest",
        lambda *_: (
            Path("registry.json"),
            [{"laneId": TENANT_A}, {"laneId": TENANT_B}],
            [],
            rollback_digests,
        ),
    )

    plan = deployment_plan.build_dry_run(
        {}, Path("manifest.json"), simulated_failure=f"06-mcp-{TENANT_A}"
    )
    actions = {action["laneId"]: action for action in plan["rollbackActions"]}

    assert actions[TENANT_A]["selectedForSimulatedRestore"] is True
    assert actions[TENANT_B]["selectedForSimulatedRestore"] is False
    assert actions[TENANT_B]["snapshotDigest"] == rollback_digests[TENANT_B]
    assert plan["failureHandling"]["unaffectedLaneTopologyChanged"] is False
