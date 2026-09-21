"""Deterministic pre-activation evidence and proof evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from .models import (
    TENANT_A,
    TENANT_B,
    SourceSignalProofRecord,
    TargetCapabilityEvidence,
)

_REQUIRED_LANES = frozenset({TENANT_A, TENANT_B})

HTTP_MCP_PASSTHROUGH_DOCUMENTATION_URL = (
    "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/"
    "gateway-target-http-passthrough.html"
)
JWT_PASSTHROUGH_DOCUMENTATION_URL = (
    "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/"
    "gateway-building-adding-targets-authorization.html"
)
@dataclass(frozen=True, slots=True)
class SourceSignalEvaluation:
    """Fail-closed classification produced from all three proof layers."""

    lane_id: str
    candidate_mechanism: str
    classification: str
    same_lane_gateway_restriction_claimed: bool


def record_target_capability_evidence(
    lane_id: str,
    deployed_target: Mapping[str, Any],
    expected_endpoint: str,
    *,
    retrieval_date: date | None = None,
) -> TargetCapabilityEvidence:
    """Record official sources and exact deployed target readback evidence.

    Args:
        lane_id: Fixed tenant lane being evaluated.
        deployed_target: Target read back from AgentCore control plane.
        expected_endpoint: Composed MCP Runtime invocation URL for the lane.
        retrieval_date: Actual date the official sources were retrieved. Defaults
            to the date this evidence is recorded.

    Returns:
        Immutable target capability evidence. Validation remains a separate,
        fail-closed step so incompatible deployed readbacks can be recorded.
    """
    target_configuration = deployed_target.get("targetConfiguration")
    passthrough: Mapping[str, Any] = {}
    if isinstance(target_configuration, Mapping):
        http = target_configuration.get("http")
        if isinstance(http, Mapping):
            candidate = http.get("passthrough")
            if isinstance(candidate, Mapping):
                passthrough = candidate

    credentials = deployed_target.get("credentialProviderConfigurations")
    credential_type = ""
    if (
        isinstance(credentials, list)
        and len(credentials) == 1
        and isinstance(credentials[0], Mapping)
    ):
        value = credentials[0].get("credentialProviderType")
        if isinstance(value, str):
            credential_type = value

    endpoint = passthrough.get("endpoint")
    protocol_type = passthrough.get("protocolType")
    deployed_evidence = {
        "targetConfiguration": target_configuration,
        "credentialProviderConfigurations": credentials,
    }
    return TargetCapabilityEvidence(
        lane_id=lane_id,
        target_type="http_passthrough" if passthrough else "incompatible",
        documentation_url=HTTP_MCP_PASSTHROUGH_DOCUMENTATION_URL,
        jwt_passthrough_documentation_url=JWT_PASSTHROUGH_DOCUMENTATION_URL,
        retrieval_date=retrieval_date or date.today(),
        protocol_type=protocol_type if isinstance(protocol_type, str) else "",
        credential_provider_type=credential_type,
        endpoint=endpoint if isinstance(endpoint, str) else "",
        deployed_configuration_evidence=json.dumps(
            deployed_evidence, sort_keys=True, separators=(",", ":")
        ),
        expected_endpoint=expected_endpoint,
        endpoint_matches=endpoint == expected_endpoint,
    )


def verify_target_capability_evidence(
    evidence: TargetCapabilityEvidence,
    *,
    as_of: date | None = None,
) -> TargetCapabilityEvidence:
    """Require official evidence and exact deployed HTTP MCP target equality."""
    valid = (
        evidence.lane_id in _REQUIRED_LANES
        and evidence.target_type == "http_passthrough"
        and evidence.documentation_url == HTTP_MCP_PASSTHROUGH_DOCUMENTATION_URL
        and evidence.jwt_passthrough_documentation_url
        == JWT_PASSTHROUGH_DOCUMENTATION_URL
        and evidence.retrieval_date <= (as_of or date.today())
        and evidence.protocol_type == "MCP"
        and evidence.credential_provider_type == "JWT_PASSTHROUGH"
        and bool(evidence.deployed_configuration_evidence)
        and bool(evidence.expected_endpoint)
        and evidence.endpoint == evidence.expected_endpoint
        and evidence.endpoint_matches
    )
    if not valid:
        raise ValueError(f"{evidence.lane_id} target capability evidence is incomplete")
    return evidence


def evaluate_source_signal_proof(
    proof: SourceSignalProofRecord,
    deployed_configuration: Mapping[str, Any] | None,
) -> SourceSignalEvaluation:
    """Classify a source mechanism only after documentation, config, and behavior.

    The mechanism name, including ``allowedWorkloadConfiguration`` or a
    documented equivalent, is only a candidate. It is never evidence by itself.
    """
    documented = (
        bool(proof.candidate_mechanism.strip())
        and bool(proof.documentation_evidence.strip())
        and proof.exact_topology_documented
    )
    configured = (
        bool(proof.deployed_configuration_evidence.strip())
        and proof.same_lane_configuration_verified
        and isinstance(deployed_configuration, Mapping)
        and bool(deployed_configuration)
    )
    behavioral = (
        proof.behavioral_verified
        and proof.missing_source_rejected_before_protected_behavior
        and proof.wrong_lane_source_rejected_before_protected_behavior
    )
    available = documented and configured and behavioral
    if proof.source_signal_available != available:
        raise ValueError(
            f"{proof.lane_id} source signal recorded classification does not match evidence"
        )
    return SourceSignalEvaluation(
        lane_id=proof.lane_id,
        candidate_mechanism=proof.candidate_mechanism,
        classification="available" if available else "unavailable",
        same_lane_gateway_restriction_claimed=available,
    )
