#!/usr/bin/env python3
"""Render fail-closed two-lane AgentCore Runtime deployment configuration."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from sage_identity import (
    AUTHORIZATION_HEADER,
    CORRELATION_HEADER,
    TENANT_A,
    TENANT_B,
    ManagedDoor,
    SourceSignalProofRecord,
    TenantLaneConfiguration,
    evaluate_source_signal_proof,
    render_lane_authorizers,
)

_REQUIRED_LANES = frozenset({TENANT_A, TENANT_B})
_CANONICAL_TENANT_CLAIM = "custom:tenant_id"


def _text(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _string_set(record: dict[str, Any], field: str) -> frozenset[str]:
    value = record.get(field)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{field} must be a non-empty string list")
    return frozenset(value)


def _lane(record: dict[str, Any]) -> TenantLaneConfiguration:
    return TenantLaneConfiguration(
        lane_id=_text(record, "laneId"),
        tenant_id=_text(record, "tenantId"),
        user_pool_id=_text(record, "userPoolId"),
        issuer=_text(record, "issuer"),
        discovery_url=_text(record, "discoveryUrl"),
        frontend_client_ids=_string_set(record, "frontendClientIds"),
        agent_runtime_endpoint=_text(record, "agentRuntimeEndpoint"),
        agent_runtime_id=_text(record, "agentRuntimeId"),
        gateway_id=_text(record, "gatewayId"),
        gateway_target_url=_text(record, "gatewayTargetUrl"),
        mcp_runtime_id=_text(record, "mcpRuntimeId"),
        expected_tenant_claim=_text(record, "expectedTenantClaim"),
    )


def _proof(record: dict[str, Any]) -> SourceSignalProofRecord:
    return SourceSignalProofRecord(
        lane_id=_text(record, "laneId"),
        candidate_mechanism=_text(record, "candidateMechanism"),
        documentation_evidence=_text(record, "documentationEvidence"),
        deployed_configuration_evidence=_text(
            record, "deployedConfigurationEvidence"
        ),
        behavioral_verified=record.get("behavioralVerified") is True,
        source_signal_available=record.get("sourceSignalAvailable") is True,
        exact_topology_documented=record.get("exactTopologyDocumented") is True,
        same_lane_configuration_verified=(
            record.get("sameLaneConfigurationVerified") is True
        ),
        missing_source_rejected_before_protected_behavior=(
            record.get("missingSourceRejectedBeforeProtectedBehavior") is True
        ),
        wrong_lane_source_rejected_before_protected_behavior=(
            record.get("wrongLaneSourceRejectedBeforeProtectedBehavior") is True
        ),
    )


def _validate_lanes(lanes: tuple[TenantLaneConfiguration, ...]) -> None:
    if len(lanes) != 2 or {lane.lane_id for lane in lanes} != _REQUIRED_LANES:
        raise ValueError("configuration must contain exactly Tenant_A and Tenant_B")
    if any(lane.lane_id != lane.tenant_id for lane in lanes):
        raise ValueError("each lane must bind its matching tenant")

    for field in (
        "user_pool_id",
        "issuer",
        "discovery_url",
        "agent_runtime_endpoint",
        "agent_runtime_id",
        "gateway_id",
        "gateway_target_url",
        "mcp_runtime_id",
        "expected_tenant_claim",
    ):
        if len({getattr(lane, field) for lane in lanes}) != 2:
            raise ValueError(f"lane {field} values must be distinct")


def _source_control(
    proof_record: dict[str, Any], proof: SourceSignalProofRecord
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    candidate_configuration = proof_record.get(proof.candidate_mechanism)
    evaluation = evaluate_source_signal_proof(
        proof,
        candidate_configuration
        if isinstance(candidate_configuration, dict)
        else None,
    )
    control = {
        "candidateMechanism": evaluation.candidate_mechanism,
        "classification": evaluation.classification,
        "sameLaneGatewayRestrictionClaimed": (
            evaluation.same_lane_gateway_restriction_claimed
        ),
    }
    return (
        copy.deepcopy(candidate_configuration)
        if evaluation.same_lane_gateway_restriction_claimed
        else None,
        control,
    )


def render_deployments(
    configuration: dict[str, Any], component: str
) -> list[dict[str, Any]]:
    """Render lane-specific Agent or MCP Runtime configuration.

    Args:
        configuration: Deployment-owned two-lane identity configuration.
        component: Either ``agent`` or ``mcp``.

    Returns:
        Exactly two component configurations ordered by lane ID.

    Raises:
        ValueError: If the two-lane binding or source proof is invalid.
    """
    if component not in {"agent", "gateway", "mcp"}:
        raise ValueError("component must be agent, gateway, or mcp")

    claim_name = _text(configuration, "canonicalTenantClaimName")
    if claim_name != _CANONICAL_TENANT_CLAIM:
        raise ValueError("canonicalTenantClaimName must be custom:tenant_id")
    accepted_tenants = _string_set(configuration, "acceptedTenantIds")
    if accepted_tenants != _REQUIRED_LANES:
        raise ValueError("acceptedTenantIds must contain exactly Tenant_A and Tenant_B")

    raw_lanes = configuration.get("lanes")
    raw_proofs = configuration.get("sourceSignalProofs")
    if not isinstance(raw_lanes, list) or not all(
        isinstance(record, dict) for record in raw_lanes
    ):
        raise ValueError("lanes must be a list of records")
    if not isinstance(raw_proofs, list) or not all(
        isinstance(record, dict) for record in raw_proofs
    ):
        raise ValueError("sourceSignalProofs must be a list of records")

    lanes = tuple(_lane(record) for record in raw_lanes)
    _validate_lanes(lanes)
    proofs = tuple(_proof(record) for record in raw_proofs)
    if len(proofs) != 2 or {proof.lane_id for proof in proofs} != _REQUIRED_LANES:
        raise ValueError("sourceSignalProofs must cover exactly both lanes")

    proof_records = {record["laneId"]: record for record in raw_proofs}
    proofs_by_lane = {proof.lane_id: proof for proof in proofs}
    rendered: list[dict[str, Any]] = []

    for lane in sorted(lanes, key=lambda item: item.lane_id):
        authorizers = render_lane_authorizers(lane)
        environment: dict[str, str] = {}
        common = {
            "laneId": lane.lane_id,
            "tenantId": lane.tenant_id,
            "runtimeEndpoint": lane.agent_runtime_endpoint,
            "requestHeaderAllowlist": [AUTHORIZATION_HEADER, CORRELATION_HEADER],
            "environment": environment,
        }

        if component == "agent":
            environment["GATEWAY_URL"] = lane.gateway_target_url
            rendered.append(
                {
                    **common,
                    "runtimeName": lane.agent_runtime_id,
                    "gatewayId": lane.gateway_id,
                    "authorizerConfig": authorizers[
                        ManagedDoor.AGENT_RUNTIME.value
                    ],
                }
            )
            continue

        if component == "gateway":
            rendered.append(
                {
                    "laneId": lane.lane_id,
                    "gatewayId": lane.gateway_id,
                    "authorizerConfig": authorizers[ManagedDoor.GATEWAY.value],
                }
            )
            continue

        environment.update(
            {
                "SAGE_LANE_ID": lane.lane_id,
                "SAGE_EXPECTED_TENANT": lane.expected_tenant_claim,
                "SAGE_CANONICAL_TENANT_CLAIM": claim_name,
            }
        )

        candidate_configuration, source_control = _source_control(
            proof_records[lane.lane_id], proofs_by_lane[lane.lane_id]
        )
        authorizer = authorizers[ManagedDoor.MCP_RUNTIME.value]
        if candidate_configuration is not None:
            authorizer["customJWTAuthorizer"][
                proofs_by_lane[lane.lane_id].candidate_mechanism
            ] = candidate_configuration
        rendered.append(
            {
                **common,
                "runtimeName": lane.mcp_runtime_id,
                "gatewayId": lane.gateway_id,
                "authorizerConfig": authorizer,
                "sourceSignalControl": source_control,
            }
        )

    return rendered


def main() -> None:
    """Render JSON configuration for shell deployment scripts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--component", choices=("agent", "gateway", "mcp"), required=True
    )
    args = parser.parse_args()

    configuration = json.loads(args.config.read_text(encoding="utf-8"))
    print(json.dumps(render_deployments(configuration, args.component), sort_keys=True))


if __name__ == "__main__":
    main()
