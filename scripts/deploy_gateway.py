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
import time
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
from botocore.exceptions import ClientError

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
    """Compose the deployed MCP Runtime base URL for a passthrough endpoint.

    The qualifier is deliberately NOT appended as a query string. A gateway
    passthrough target forwards to ``{endpoint}/{path}``, so any query string on
    the endpoint would be split by the appended path (producing
    ``?qualifier=DEFAULT/invocations``). The qualifier is supplied separately via
    ``staticQueryParameters`` so the gateway appends it after the path instead.

    Args:
        region: AWS Region containing the deployed Runtime.
        runtime_arn: Deployed MCP Runtime ARN.
        qualifier: Deployed Runtime qualifier, validated but not embedded here.

    Returns:
        The MCP Runtime base URL, without ``/invocations`` and without a query
        string.

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
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}"
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
                "staticQueryParameters": {"qualifier": qualifier},
                "staticQueryParameterConflictResolution": "STATIC_OVERRIDE",
            }
        }
    }
    if target.get("targetConfiguration") != expected_configuration:
        raise ValueError(
            "target must be HTTP passthrough protocolType MCP with the exact "
            "unqualified Runtime endpoint and a static qualifier parameter"
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
                        "staticQueryParameters": {"qualifier": qualifier},
                        "staticQueryParameterConflictResolution": "STATIC_OVERRIDE",
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


GATEWAY_ROLE_NAME = "sage-gateway-role"
GATEWAY_INVOKE_POLICY_NAME = "SageGatewayInvokeMcpRuntimes"


def gateway_trust_policy(account_id: str, region: str) -> dict[str, Any]:
    """Build the documented Gateway trust policy with confused-deputy guards.

    AWS documents ``aws:SourceAccount`` and ``aws:SourceArn`` conditions for the
    AgentCore Gateway execution role. Without them any AgentCore gateway in any
    account could ask the service to assume this role.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/*"
                        )
                    },
                },
            }
        ],
    }


def gateway_invoke_policy(account_id: str, region: str) -> dict[str, Any]:
    """Build the least-privilege outbound policy for Sage MCP Runtime targets.

    A ``JWT_PASSTHROUGH`` target forwards the caller's bearer, so the Gateway
    should not need SigV4 authority over the Runtime. This grant is retained as
    a narrow fallback while that is confirmed behaviourally, and is scoped to the
    two Sage MCP Runtimes rather than every runtime in the account.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeSageMcpRuntimes",
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/sage_mcp_*"
                ],
            }
        ],
    }


def ensure_gateway_role(iam: Any, account_id: str, region: str) -> str:
    """Create or reconcile the Gateway execution role and return its ARN."""
    trust = json.dumps(gateway_trust_policy(account_id, region))
    try:
        role = iam.get_role(RoleName=GATEWAY_ROLE_NAME)["Role"]
        # Reconcile an existing role that may predate the trust conditions.
        iam.update_assume_role_policy(
            RoleName=GATEWAY_ROLE_NAME, PolicyDocument=trust
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
            raise
        role = iam.create_role(
            RoleName=GATEWAY_ROLE_NAME,
            AssumeRolePolicyDocument=trust,
            Description="Sage AgentCore Gateway execution role",
        )["Role"]

    iam.put_role_policy(
        RoleName=GATEWAY_ROLE_NAME,
        PolicyName=GATEWAY_INVOKE_POLICY_NAME,
        PolicyDocument=json.dumps(gateway_invoke_policy(account_id, region)),
    )
    return str(role["Arn"])


def ensure_gateways(
    configuration: Mapping[str, Any],
    agentcore: Any,
    iam: Any,
    account_id: str,
) -> dict[str, str]:
    """Create any missing lane Gateway with its own same-lane JWT authorizer.

    ``deploy_gateway_targets`` configures Gateways that already exist, so this
    closes the gap that previously required manual creation.
    """
    region = _required_text(configuration, "region")
    role_arn = ensure_gateway_role(iam, account_id, region)
    authorizers = {
        item["laneId"]: item["authorizerConfig"]
        for item in render_deployments(dict(configuration), "gateway")
    }

    existing = {
        gateway.get("name"): gateway.get("gatewayId")
        for gateway in agentcore.list_gateways(maxResults=100).get("items", [])
    }
    created: dict[str, str] = {}
    for lane_id in sorted(_REQUIRED_LANES):
        name = f"sage-gw-{lane_id.replace('_', '-').lower()}"
        if name in existing:
            created[lane_id] = str(existing[name])
            continue
        # protocolType is deliberately omitted. Setting it to MCP — the only
        # accepted value — makes the service reject HTTP target configurations
        # with "HTTP target configuration is not supported for gateways with MCP
        # protocol type". A gateway created without it accepts the HTTP
        # passthrough target this architecture requires.
        response = agentcore.create_gateway(
            name=name,
            roleArn=role_arn,
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration=authorizers[lane_id],
        )
        created[lane_id] = str(response["gatewayId"])
    return created


def _wait_for_gateway_ready(
    client: Any, gateway_id: str, *, attempts: int = 40, delay: float = 5.0
) -> None:
    """Block until a Gateway leaves a transitional status.

    UpdateGateway puts the Gateway into UPDATING, and CreateGatewayTarget is
    rejected while that lasts.
    """
    for _ in range(attempts):
        status = client.get_gateway(gatewayIdentifier=gateway_id).get("status")
        if status == "READY":
            return
        if status in {"FAILED", "UPDATE_UNSUCCESSFUL", "DELETING"}:
            raise ValueError(f"gateway {gateway_id} is in status {status}")
        time.sleep(delay)
    raise ValueError(f"gateway {gateway_id} did not become READY in time")


def apply_gateway_authorizer(
    client: Any, gateway_id: str, authorizer: Mapping[str, Any]
) -> None:
    """Replace one existing Gateway's inbound policy and verify the readback."""
    current = client.get_gateway(gatewayIdentifier=gateway_id)
    parameters: dict[str, Any] = {
        "gatewayIdentifier": gateway_id,
        "name": _required_text(current, "name"),
        "roleArn": _required_text(current, "roleArn"),
        "authorizerType": "CUSTOM_JWT",
        "authorizerConfiguration": dict(authorizer),
    }
    # Gateways that accept HTTP passthrough targets carry no protocolType, and
    # UpdateGateway rejects an empty value, so it is only sent when present.
    protocol_type = current.get("protocolType")
    if isinstance(protocol_type, str) and protocol_type.strip():
        parameters["protocolType"] = protocol_type
    client.update_gateway(**parameters)
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
        _wait_for_gateway_ready(agentcore, request["gatewayIdentifier"])
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
    parser.add_argument(
        "--ensure-gateways",
        action="store_true",
        help="Create the Gateway role and any missing lane Gateway, then exit.",
    )
    args = parser.parse_args()

    configuration = json.loads(args.config.read_text(encoding="utf-8"))
    if args.render:
        print(json.dumps(render_gateway_targets(configuration), sort_keys=True))
        return

    if args.ensure_gateways:
        region = _required_text(configuration, "region")
        account_id = boto3.client("sts").get_caller_identity()["Account"]
        gateways = ensure_gateways(
            configuration,
            boto3.client("bedrock-agentcore-control", region_name=region),
            boto3.client("iam"),
            account_id,
        )
        print(json.dumps(gateways, indent=2, sort_keys=True))
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
