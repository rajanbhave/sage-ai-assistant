#!/usr/bin/env python3
"""Render or deploy two lane-local AgentCore HTTP MCP passthrough targets.

The deployment configuration must contain exactly Tenant_A and Tenant_B. Each
lane supplies its existing Gateway ID, deployed MCP Runtime ARN, and deployed
Runtime qualifier. This script creates no Cognito, M2M, OAuth credential, or
semantic MCP resources.

Usage:
  uv run python scripts/deploy_gateway.py --render
  uv run python scripts/deploy_gateway.py
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.parse
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force IPv4 — macOS often resolves AWS endpoints to IPv6 but the route hangs.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
    results = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [result for result in results if result[0] == socket.AF_INET]
    return ipv4 if ipv4 else results


socket.getaddrinfo = _ipv4_getaddrinfo

import boto3

from sage_identity import (
    TENANT_A,
    TENANT_B,
    record_target_capability_evidence,
    verify_target_capability_evidence,
)
from scripts.render_identity_deployments import render_deployments

SCRIPT_DIR = PROJECT_ROOT / "scripts"
DEFAULT_CONFIG_FILE = SCRIPT_DIR / "identity_deployment.json"
OUTPUT_FILE = SCRIPT_DIR / "gateway_output.json"
_REQUIRED_LANES = frozenset({TENANT_A, TENANT_B})
_TARGET_CREDENTIALS = [{"credentialProviderType": "JWT_PASSTHROUGH"}]


def _required_text(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def compose_mcp_runtime_invocation_url(
    region: str, runtime_arn: str, qualifier: str
) -> str:
    """Compose the exact deployed MCP Runtime invocation URL.

    Args:
        region: AWS Region containing the deployed Runtime.
        runtime_arn: Deployed MCP Runtime ARN.
        qualifier: Deployed Runtime qualifier.

    Returns:
        The exact AgentCore Runtime invocation URL.

    Raises:
        ValueError: If any component is missing or the ARN is not a Runtime in
            the supplied Region.
    """
    if not region.strip():
        raise ValueError("region must be a non-empty string")
    if not qualifier.strip():
        raise ValueError("mcpRuntimeQualifier must be a non-empty string")

    arn_parts = runtime_arn.split(":", 5)
    if (
        len(arn_parts) != 6
        or arn_parts[0] != "arn"
        or arn_parts[2] != "bedrock-agentcore"
        or arn_parts[3] != region
        or not arn_parts[4]
        or not arn_parts[5].startswith("runtime/")
        or not arn_parts[5].removeprefix("runtime/")
    ):
        raise ValueError("mcpRuntimeArn must be a deployed AgentCore Runtime ARN in region")

    encoded_arn = urllib.parse.quote(runtime_arn, safe="")
    encoded_qualifier = urllib.parse.quote(qualifier, safe="")
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
        f"{encoded_arn}/invocations?qualifier={encoded_qualifier}"
    )


def validate_passthrough_target(
    target: Mapping[str, Any],
    *,
    region: str,
    runtime_arn: str,
    qualifier: str,
) -> None:
    """Reject any target that is not the exact HTTP MCP passthrough shape."""
    expected_endpoint = compose_mcp_runtime_invocation_url(
        region, runtime_arn, qualifier
    )
    expected_configuration = {
        "http": {
            "passthrough": {
                "endpoint": expected_endpoint,
                "protocolType": "MCP",
            }
        }
    }
    if target.get("targetConfiguration") != expected_configuration:
        raise ValueError(
            "target must be HTTP passthrough protocolType MCP with the exact qualified Runtime endpoint"
        )
    if target.get("credentialProviderConfigurations") != _TARGET_CREDENTIALS:
        raise ValueError("target credential provider must be exactly JWT_PASSTHROUGH")


def render_gateway_targets(
    configuration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Render exactly two validated lane-local HTTP MCP target requests."""
    region = _required_text(configuration, "region")
    raw_lanes = configuration.get("lanes")
    if not isinstance(raw_lanes, list) or not all(
        isinstance(lane, dict) for lane in raw_lanes
    ):
        raise ValueError("lanes must be a list of records")

    lane_ids = {
        lane.get("laneId") for lane in raw_lanes if isinstance(lane, dict)
    }
    if len(raw_lanes) != 2 or lane_ids != _REQUIRED_LANES:
        raise ValueError("configuration must contain exactly Tenant_A and Tenant_B")

    gateway_ids = [_required_text(lane, "gatewayId") for lane in raw_lanes]
    runtime_arns = [_required_text(lane, "mcpRuntimeArn") for lane in raw_lanes]
    if len(set(gateway_ids)) != 2:
        raise ValueError("gatewayId values must be distinct")
    if len(set(runtime_arns)) != 2:
        raise ValueError("mcpRuntimeArn values must be distinct")

    targets: list[dict[str, Any]] = []
    for lane in sorted(raw_lanes, key=lambda item: item["laneId"]):
        lane_id = _required_text(lane, "laneId")
        runtime_arn = _required_text(lane, "mcpRuntimeArn")
        qualifier = _required_text(lane, "mcpRuntimeQualifier")
        endpoint = compose_mcp_runtime_invocation_url(region, runtime_arn, qualifier)
        target = {
            "gatewayIdentifier": _required_text(lane, "gatewayId"),
            "name": f"sage-mcp-{lane_id.lower().replace('_', '-')}",
            "description": f"{lane_id} Sage MCP Runtime HTTP passthrough",
            "targetConfiguration": {
                "http": {
                    "passthrough": {
                        "endpoint": endpoint,
                        "protocolType": "MCP",
                    }
                }
            },
            "credentialProviderConfigurations": [
                {"credentialProviderType": "JWT_PASSTHROUGH"}
            ],
        }
        validate_passthrough_target(
            target,
            region=region,
            runtime_arn=runtime_arn,
            qualifier=qualifier,
        )
        targets.append({"laneId": lane_id, **target})

    return targets


def apply_gateway_authorizer(
    client: Any, gateway_id: str, authorizer: Mapping[str, Any]
) -> None:
    """Replace one existing Gateway's inbound policy and verify the readback."""
    current = client.get_gateway(gatewayIdentifier=gateway_id)
    client.update_gateway(
        gatewayIdentifier=gateway_id,
        name=_required_text(current, "name"),
        roleArn=_required_text(current, "roleArn"),
        protocolType=_required_text(current, "protocolType"),
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration=dict(authorizer),
    )
    updated = client.get_gateway(gatewayIdentifier=gateway_id)
    if (
        updated.get("authorizerType") != "CUSTOM_JWT"
        or updated.get("authorizerConfiguration") != authorizer
    ):
        raise ValueError("Gateway managed authorizer readback does not match its lane")


def deploy_gateway_targets(
    configuration: Mapping[str, Any],
    client: Any | None = None,
    *,
    retrieval_date: date | None = None,
) -> list[dict[str, Any]]:
    """Apply lane authorizers, create targets, and verify deployed evidence."""
    region = _required_text(configuration, "region")
    agentcore = client or boto3.client(
        "bedrock-agentcore-control", region_name=region
    )
    gateway_authorizers = {
        item["laneId"]: item for item in render_deployments(dict(configuration), "gateway")
    }
    outputs: list[dict[str, Any]] = []
    lane_records = {
        _required_text(lane, "laneId"): lane
        for lane in configuration["lanes"]
    }
    for rendered in render_gateway_targets(configuration):
        lane_id = rendered["laneId"]
        request = {key: value for key, value in rendered.items() if key != "laneId"}
        apply_gateway_authorizer(
            agentcore,
            request["gatewayIdentifier"],
            gateway_authorizers[lane_id]["authorizerConfig"],
        )
        response = agentcore.create_gateway_target(**request)
        target_id = response["targetId"]
        deployed = agentcore.get_gateway_target(
            gatewayIdentifier=request["gatewayIdentifier"], targetId=target_id
        )
        lane = lane_records[lane_id]
        validate_passthrough_target(
            deployed,
            region=region,
            runtime_arn=_required_text(lane, "mcpRuntimeArn"),
            qualifier=_required_text(lane, "mcpRuntimeQualifier"),
        )
        expected_endpoint = request["targetConfiguration"]["http"]["passthrough"][
            "endpoint"
        ]
        evidence = record_target_capability_evidence(
            lane_id,
            deployed,
            expected_endpoint,
            retrieval_date=retrieval_date,
        )
        verify_target_capability_evidence(evidence)
        outputs.append(
            {
                "laneId": lane_id,
                "gatewayId": request["gatewayIdentifier"],
                "targetId": target_id,
                "status": deployed.get("status", response.get("status", "unknown")),
                "mcpRuntimeInvocationUrl": expected_endpoint,
                "targetEvidence": {
                    "targetType": evidence.target_type,
                    "documentationUrls": [
                        evidence.documentation_url,
                        evidence.jwt_passthrough_documentation_url,
                    ],
                    "retrievalDate": evidence.retrieval_date.isoformat(),
                    "deployedConfigurationEvidence": (
                        evidence.deployed_configuration_evidence
                    ),
                    "protocolType": evidence.protocol_type,
                    "credentialProviderType": evidence.credential_provider_type,
                    "endpoint": evidence.endpoint,
                    "expectedEndpoint": evidence.expected_endpoint,
                    "endpointMatches": evidence.endpoint_matches,
                },
            }
        )
    return outputs


def main() -> None:
    """Render locally or deploy the exact two-lane target configuration."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            os.environ.get("SAGE_IDENTITY_CONFIG_FILE", DEFAULT_CONFIG_FILE)
        ),
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    configuration = json.loads(args.config.read_text(encoding="utf-8"))
    if args.render:
        print(json.dumps(render_gateway_targets(configuration), sort_keys=True))
        return

    outputs = deploy_gateway_targets(configuration)
    OUTPUT_FILE.write_text(
        json.dumps(
            {"region": _required_text(configuration, "region"), "lanes": outputs},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Created {len(outputs)} HTTP MCP passthrough targets.")


if __name__ == "__main__":
    main()
