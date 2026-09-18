#!/usr/bin/env python3
"""Configure two existing Cognito pools for Sage access-token issuance.

The script never creates a user pool. It first verifies both existing pools,
their active feature plans, and their active V2_0 pre-token-generation
customizers. Only after both lanes pass preflight does it create Sage
resource scopes and one public browser client per pool.

Required environment variables for each ``TENANT_A`` and ``TENANT_B`` prefix:

- ``<prefix>_USER_POOL_ID``
- ``<prefix>_PRE_TOKEN_LAMBDA_ARN`` (qualified alias/version ARN)
- ``<prefix>_PRE_TOKEN_LAMBDA_CODE_SHA256``
- ``<prefix>_TRUSTED_ASSIGNMENT_ATTRIBUTE``
- ``<prefix>_AGENT_RUNTIME_ENDPOINT``
- ``<prefix>_APPROVED_ACCESS_TOKEN_VALIDITY``
- ``<prefix>_APPROVED_ACCESS_TOKEN_VALIDITY_UNIT``
- ``<prefix>_TOKEN_LIFETIME_APPROVAL_REFERENCE``

The approved validity value has no default. Its deployed value and unit must
match the customer-approved input exactly.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Force IPv4 — macOS often resolves AWS endpoints to IPv6 but the route hangs.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
    """Prefer IPv4 addresses to avoid macOS IPv6 routing issues."""
    results = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [result for result in results if result[0] == socket.AF_INET]
    return ipv4 if ipv4 else results


socket.getaddrinfo = _ipv4_getaddrinfo

import boto3

from sage_identity import load_access_token_customizer_configuration

REGION = os.environ.get("AWS_REGION", "us-east-1")
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "user_pool_output.json"
CANONICAL_TENANT_CLAIM_NAME = "custom:tenant_id"
LANE_IDS = ("Tenant_A", "Tenant_B")
SUPPORTED_ACCESS_TOKEN_TIERS = frozenset({"ESSENTIALS", "PLUS"})
PUBLIC_AUTH_FLOWS = (
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
)
TOKEN_VALIDITY_UNITS = frozenset({"seconds", "minutes", "hours", "days"})
RESOURCE_SERVERS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    ("sage-agent", "Sage Agent", (("invoke", "Invoke the Sage Agent"),)),
    ("sage-gateway", "Sage Gateway", (("invoke", "Invoke the Sage Gateway"),)),
    ("sage-mcp", "Sage MCP", (("invoke", "Invoke Sage MCP tools"),)),
    (
        "sage-api",
        "Sage API",
        (("read", "Read tenant data"), ("write", "Change tenant data")),
    ),
)
SAGE_SCOPES = tuple(
    f"{identifier}/{scope_name}"
    for identifier, _, scopes in RESOURCE_SERVERS
    for scope_name, _ in scopes
)


@dataclass(frozen=True, slots=True)
class LaneInput:
    """Customer-approved deployment inputs for one fixed tenant lane."""

    lane_id: str
    tenant_id: str
    user_pool_id: str
    client_name: str
    expected_tenant_claim: str
    trusted_assignment_attribute: str
    pre_token_lambda_arn: str
    pre_token_lambda_code_sha256: str
    agent_runtime_endpoint: str
    approved_access_token_validity: int
    approved_access_token_validity_unit: str
    token_lifetime_approval_reference: str


@dataclass(frozen=True, slots=True)
class LanePreflight:
    """Read-only evidence captured before any Cognito mutation."""

    lane: LaneInput
    feature_plan: str
    pre_token_lambda_arn: str
    pre_token_lambda_version: str
    pre_token_lambda_code_sha256: str
    existing_client_id: str | None


@dataclass(frozen=True, slots=True)
class TrustedLaneRecord:
    """Immutable browser trust record emitted for one tenant lane."""

    laneId: str
    tenantId: str
    userPoolId: str
    issuer: str
    discoveryUrl: str
    frontendClientIds: tuple[str, ...]
    agentRuntimeEndpoint: str
    expectedTenantClaim: str
    trustedAssignmentSource: str


@dataclass(frozen=True, slots=True)
class TokenLifetimeEvidence:
    """Machine-readable approved and active access-token lifetime evidence."""

    laneId: str
    activeValue: int
    activeUnit: str
    documentedValue: int
    documentedUnit: str
    approvalReference: str


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required configuration: {name}")
    return value


def load_lane_inputs(environment: Mapping[str, str] = os.environ) -> tuple[LaneInput, ...]:
    """Load exactly the two fixed lane records from trusted deployment input."""
    lanes: list[LaneInput] = []
    for lane_id in LANE_IDS:
        prefix = lane_id.upper()
        validity_text = _required(
            environment, f"{prefix}_APPROVED_ACCESS_TOKEN_VALIDITY"
        )
        try:
            validity = int(validity_text)
        except ValueError as error:
            raise ValueError(
                f"{prefix}_APPROVED_ACCESS_TOKEN_VALIDITY must be an integer"
            ) from error
        if validity <= 0:
            raise ValueError(
                f"{prefix}_APPROVED_ACCESS_TOKEN_VALIDITY must be positive"
            )
        validity_unit = _required(
            environment, f"{prefix}_APPROVED_ACCESS_TOKEN_VALIDITY_UNIT"
        ).lower()
        if validity_unit not in TOKEN_VALIDITY_UNITS:
            raise ValueError(
                f"{prefix}_APPROVED_ACCESS_TOKEN_VALIDITY_UNIT is invalid"
            )
        suffix = lane_id[-1].lower()
        lanes.append(
            LaneInput(
                lane_id=lane_id,
                tenant_id=lane_id,
                user_pool_id=_required(environment, f"{prefix}_USER_POOL_ID"),
                client_name=f"sage-tenant-{suffix}-client",
                expected_tenant_claim=lane_id,
                trusted_assignment_attribute=_required(
                    environment, f"{prefix}_TRUSTED_ASSIGNMENT_ATTRIBUTE"
                ),
                pre_token_lambda_arn=_required(
                    environment, f"{prefix}_PRE_TOKEN_LAMBDA_ARN"
                ),
                pre_token_lambda_code_sha256=_required(
                    environment, f"{prefix}_PRE_TOKEN_LAMBDA_CODE_SHA256"
                ),
                agent_runtime_endpoint=_required(
                    environment, f"{prefix}_AGENT_RUNTIME_ENDPOINT"
                ),
                approved_access_token_validity=validity,
                approved_access_token_validity_unit=validity_unit,
                token_lifetime_approval_reference=_required(
                    environment, f"{prefix}_TOKEN_LIFETIME_APPROVAL_REFERENCE"
                ),
            )
        )
    _validate_lane_inputs(tuple(lanes))
    return tuple(lanes)


def _validate_lane_inputs(lanes: tuple[LaneInput, ...]) -> None:
    if len(lanes) != 2 or {lane.lane_id for lane in lanes} != set(LANE_IDS):
        raise ValueError("configuration must contain exactly Tenant_A and Tenant_B")
    if any(lane.lane_id != lane.tenant_id for lane in lanes):
        raise ValueError("each lane must bind its matching tenant")
    for field_name in ("user_pool_id", "agent_runtime_endpoint", "expected_tenant_claim"):
        if len({getattr(lane, field_name) for lane in lanes}) != 2:
            raise ValueError(f"lane {field_name} values must be distinct")


def _list_items(cognito: Any, operation: str, result_key: str, **kwargs: Any) -> list[dict[str, Any]]:
    paginator = cognito.get_paginator(operation)
    return [
        item
        for page in paginator.paginate(**kwargs)
        for item in page.get(result_key, [])
    ]


def _inspect_existing_client(cognito: Any, lane: LaneInput) -> str | None:
    matches = [
        client
        for client in _list_items(
            cognito,
            "list_user_pool_clients",
            "UserPoolClients",
            UserPoolId=lane.user_pool_id,
        )
        if client.get("ClientName") == lane.client_name
    ]
    if len(matches) > 1:
        raise ValueError(f"{lane.lane_id} has duplicate Sage public clients")
    if not matches:
        return None

    client_id = matches[0].get("ClientId")
    if not isinstance(client_id, str) or not client_id:
        raise ValueError(f"{lane.lane_id} public client has no client ID")
    client = cognito.describe_user_pool_client(
        UserPoolId=lane.user_pool_id, ClientId=client_id
    )["UserPoolClient"]
    units = client.get("TokenValidityUnits", {})
    if (
        client.get("ClientSecret")
        or set(client.get("ExplicitAuthFlows", [])) != set(PUBLIC_AUTH_FLOWS)
        or lane.trusted_assignment_attribute not in client.get("ReadAttributes", [])
        or lane.trusted_assignment_attribute in client.get("WriteAttributes", [])
        or "client_credentials" in client.get("AllowedOAuthFlows", [])
        or client.get("AccessTokenValidity")
        != lane.approved_access_token_validity
        or units.get("AccessToken")
        != lane.approved_access_token_validity_unit
    ):
        raise ValueError(
            f"{lane.lane_id} existing client is not the approved Sage public client"
        )
    return client_id


def _verify_pre_token_customizer(
    lambda_client: Any,
    lane: LaneInput,
    existing_client_id: str | None,
) -> str:
    arn_parts = lane.pre_token_lambda_arn.split(":")
    if (
        len(arn_parts) != 8
        or arn_parts[2] != "lambda"
        or arn_parts[5] != "function"
        or not arn_parts[7]
        or arn_parts[7] == "$LATEST"
    ):
        raise ValueError(
            f"{lane.lane_id} pre-token Lambda ARN must use an immutable version or alias"
        )

    response = lambda_client.get_function(FunctionName=lane.pre_token_lambda_arn)
    configuration = response.get("Configuration", {})
    code_sha256 = configuration.get("CodeSha256")
    if (
        configuration.get("Handler") != "sage_identity.cognito.lambda_handler"
        or configuration.get("Version") == "$LATEST"
        or code_sha256 != lane.pre_token_lambda_code_sha256
    ):
        raise ValueError(
            f"{lane.lane_id} pre-token Lambda code identity is not approved"
        )

    variables = configuration.get("Environment", {}).get("Variables", {})
    serialized = variables.get("SAGE_TOKEN_CUSTOMIZER_CONFIG")
    if not isinstance(serialized, str):
        raise ValueError(
            f"{lane.lane_id} pre-token Lambda configuration is missing"
        )
    customizer = load_access_token_customizer_configuration(serialized)
    if (
        customizer.user_pool_id != lane.user_pool_id
        or customizer.expected_tenant != lane.expected_tenant_claim
        or customizer.canonical_tenant_claim_name != CANONICAL_TENANT_CLAIM_NAME
        or customizer.trusted_assignment_attribute
        != lane.trusted_assignment_attribute
        or (
            existing_client_id is not None
            and existing_client_id not in customizer.trusted_client_ids
        )
    ):
        raise ValueError(
            f"{lane.lane_id} pre-token Lambda configuration is not lane-bound"
        )
    return code_sha256


def verify_lane_preflight(
    cognito: Any, lambda_client: Any, lane: LaneInput
) -> LanePreflight:
    """Verify one pool plan, V2 trigger, immutable Lambda, and client."""
    pool = cognito.describe_user_pool(UserPoolId=lane.user_pool_id)["UserPool"]
    if pool.get("Id") != lane.user_pool_id:
        raise ValueError(f"{lane.lane_id} user pool identity is invalid")

    lambda_config = pool.get("LambdaConfig", {})
    trigger = lambda_config.get("PreTokenGenerationConfig", {})
    version = trigger.get("LambdaVersion")
    lambda_arn = trigger.get("LambdaArn")
    feature_plan = pool.get("UserPoolTier")
    feature_plan_supports_v2 = feature_plan in SUPPORTED_ACCESS_TOKEN_TIERS or (
        feature_plan == "LITE" and version == "V2_0"
    )
    if not feature_plan_supports_v2:
        raise ValueError(f"{lane.lane_id} feature plan does not support V2_0")
    if version != "V2_0" or lambda_arn != lane.pre_token_lambda_arn:
        raise ValueError(
            f"{lane.lane_id} active PreTokenGeneration configuration is not V2_0"
        )

    assignment_sources = [
        attribute
        for attribute in pool.get("SchemaAttributes", [])
        if attribute.get("Name") == lane.trusted_assignment_attribute
        and attribute.get("AttributeDataType") == "String"
    ]
    if len(assignment_sources) != 1:
        raise ValueError(
            f"{lane.lane_id} must have exactly one trusted assignment source"
        )

    existing_client_id = _inspect_existing_client(cognito, lane)
    code_sha256 = _verify_pre_token_customizer(
        lambda_client, lane, existing_client_id
    )
    return LanePreflight(
        lane=lane,
        feature_plan=feature_plan,
        pre_token_lambda_arn=lambda_arn,
        pre_token_lambda_version=version,
        pre_token_lambda_code_sha256=code_sha256,
        existing_client_id=existing_client_id,
    )


def verify_all_preflight(
    cognito: Any, lambda_client: Any, lanes: tuple[LaneInput, ...]
) -> tuple[LanePreflight, ...]:
    """Verify both lanes completely before the caller can mutate Cognito."""
    _validate_lane_inputs(lanes)
    return tuple(
        verify_lane_preflight(cognito, lambda_client, lane) for lane in lanes
    )


def configure_resource_scopes(cognito: Any, pool_id: str) -> None:
    """Create or reconcile the fixed Sage custom scopes in one pool."""
    existing = {
        resource["Identifier"]: resource
        for resource in _list_items(
            cognito,
            "list_resource_servers",
            "ResourceServers",
            UserPoolId=pool_id,
        )
    }
    for identifier, name, scope_pairs in RESOURCE_SERVERS:
        scopes = [
            {"ScopeName": scope_name, "ScopeDescription": description}
            for scope_name, description in scope_pairs
        ]
        current = existing.get(identifier)
        if current and current.get("Name") == name and current.get("Scopes") == scopes:
            continue
        parameters = {
            "UserPoolId": pool_id,
            "Identifier": identifier,
            "Name": name,
            "Scopes": scopes,
        }
        if current:
            cognito.update_resource_server(**parameters)
        else:
            cognito.create_resource_server(**parameters)


def ensure_public_client(
    cognito: Any, preflight: LanePreflight
) -> tuple[str, dict[str, Any]]:
    """Create the lane's one public client, or return its verified existing client."""
    lane = preflight.lane
    if preflight.existing_client_id is None:
        response = cognito.create_user_pool_client(
            UserPoolId=lane.user_pool_id,
            ClientName=lane.client_name,
            GenerateSecret=False,
            ExplicitAuthFlows=list(PUBLIC_AUTH_FLOWS),
            ReadAttributes=[lane.trusted_assignment_attribute],
            AccessTokenValidity=lane.approved_access_token_validity,
            TokenValidityUnits={
                "AccessToken": lane.approved_access_token_validity_unit
            },
            PreventUserExistenceErrors="ENABLED",
            EnableTokenRevocation=True,
        )
        client_id = response["UserPoolClient"]["ClientId"]
    else:
        client_id = preflight.existing_client_id

    client = cognito.describe_user_pool_client(
        UserPoolId=lane.user_pool_id, ClientId=client_id
    )["UserPoolClient"]
    return client_id, client


def _issuer(pool_id: str) -> str:
    return f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}"


def build_output(
    deployed: tuple[tuple[LanePreflight, str, dict[str, Any]], ...]
) -> dict[str, object]:
    """Build exact two-lane records and approved/active lifetime evidence."""
    trusted_lanes: list[TrustedLaneRecord] = []
    lifetimes: list[TokenLifetimeEvidence] = []
    trigger_evidence: list[dict[str, str]] = []
    for preflight, client_id, client in deployed:
        lane = preflight.lane
        issuer = _issuer(lane.user_pool_id)
        units = client.get("TokenValidityUnits", {})
        active_value = client.get("AccessTokenValidity")
        active_unit = units.get("AccessToken")
        if (
            not isinstance(active_value, int)
            or not isinstance(active_unit, str)
            or active_value != lane.approved_access_token_validity
            or active_unit != lane.approved_access_token_validity_unit
        ):
            raise ValueError(
                f"{lane.lane_id} active access-token lifetime does not match approval"
            )
        trusted_lanes.append(
            TrustedLaneRecord(
                laneId=lane.lane_id,
                tenantId=lane.tenant_id,
                userPoolId=lane.user_pool_id,
                issuer=issuer,
                discoveryUrl=f"{issuer}/.well-known/openid-configuration",
                frontendClientIds=(client_id,),
                agentRuntimeEndpoint=lane.agent_runtime_endpoint,
                expectedTenantClaim=lane.expected_tenant_claim,
                trustedAssignmentSource=lane.trusted_assignment_attribute,
            )
        )
        lifetimes.append(
            TokenLifetimeEvidence(
                laneId=lane.lane_id,
                activeValue=active_value,
                activeUnit=active_unit,
                documentedValue=lane.approved_access_token_validity,
                documentedUnit=lane.approved_access_token_validity_unit,
                approvalReference=lane.token_lifetime_approval_reference,
            )
        )
        trigger_evidence.append(
            {
                "laneId": lane.lane_id,
                "featurePlan": preflight.feature_plan,
                "lambdaArn": preflight.pre_token_lambda_arn,
                "lambdaVersion": preflight.pre_token_lambda_version,
                "codeSha256": preflight.pre_token_lambda_code_sha256,
            }
        )

    if len(trusted_lanes) != 2 or {lane.laneId for lane in trusted_lanes} != set(
        LANE_IDS
    ):
        raise ValueError("output must contain exactly Tenant_A and Tenant_B")
    return {
        "region": REGION,
        "canonicalTenantClaimName": CANONICAL_TENANT_CLAIM_NAME,
        "acceptedTenantIds": list(LANE_IDS),
        "scopes": list(SAGE_SCOPES),
        "lanes": [asdict(lane) for lane in trusted_lanes],
        "tokenLifetimes": [asdict(lifetime) for lifetime in lifetimes],
        "preTokenGenerationEvidence": trigger_evidence,
    }


def deploy(
    cognito: Any, lambda_client: Any, lanes: tuple[LaneInput, ...]
) -> dict[str, object]:
    """Preflight both lanes, then configure their scopes and public clients."""
    preflights = verify_all_preflight(cognito, lambda_client, lanes)
    deployed: list[tuple[LanePreflight, str, dict[str, Any]]] = []
    for preflight in preflights:
        configure_resource_scopes(cognito, preflight.lane.user_pool_id)
        client_id, client = ensure_public_client(cognito, preflight)
        deployed.append((preflight, client_id, client))
    return build_output(tuple(deployed))


def main() -> int:
    """Configure both existing pools and save trusted tenant-lane output."""
    try:
        lanes = load_lane_inputs()
        cognito = boto3.client("cognito-idp", region_name=REGION)
        lambda_client = boto3.client("lambda", region_name=REGION)
        output = deploy(cognito, lambda_client, lanes)
        OUTPUT_FILE.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as error:
        print(f"User-pool deployment rejected: {error}", file=sys.stderr)
        return 1

    print(f"Configured exactly two existing tenant pools: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
