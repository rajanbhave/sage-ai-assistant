#!/usr/bin/env python3
"""Build a mutation-free, fail-closed identity deployment plan.

This command only reads the approved manifest and Registry output, validates
both, and emits a deterministic dry-run plan. Cloud mutation remains gated by
Task 13.5 and later deployment tasks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sage_identity import TENANT_A, TENANT_B
from scripts.deploy_gateway import render_gateway_targets
from scripts.render_identity_deployments import render_deployments

DEFAULT_MANIFEST = PROJECT_ROOT / "scripts" / "identity_deployment.json"
_REQUIRED_LANES = (TENANT_A, TENANT_B)
_REQUIRED_DOORS = {
    (TENANT_A, "agent_runtime", "sage-agent/invoke"),
    (TENANT_A, "gateway", "sage-gateway/invoke"),
    (TENANT_A, "mcp_runtime", "sage-mcp/invoke"),
    (TENANT_B, "agent_runtime", "sage-agent/invoke"),
    (TENANT_B, "gateway", "sage-gateway/invoke"),
    (TENANT_B, "mcp_runtime", "sage-mcp/invoke"),
}
_FORBIDDEN_VALUES = {
    "CLIENT_CREDENTIALS",
    "CONTEXT_TOKEN",
    "MCP_SERVER",
    "OAUTH",
    "SEMANTIC",
    "TOKEN_EXCHANGE",
    "WORKLOAD_TOKEN",
}
_SECRET_KEYS = {
    "accessToken",
    "authorization",
    "bearerToken",
    "clientSecret",
    "idToken",
    "refreshToken",
    "secret",
    "secretValue",
}


class DeploymentPlanError(ValueError):
    """A safe validation failure that prevents a deployment plan."""


def _record(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DeploymentPlanError(f"{field} must be an object")
    return value


def _records(value: Any, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise DeploymentPlanError(f"{field} must be a list of objects")
    return list(value)


def _text(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DeploymentPlanError(f"{field} must be a non-empty string")
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _walk(value: Any) -> Sequence[tuple[str | None, Any]]:
    items: list[tuple[str | None, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            items.append((str(key), child))
            items.extend(_walk(child))
    elif isinstance(value, list):
        for child in value:
            items.append((None, child))
            items.extend(_walk(child))
    return items


def _validate_secret_and_forbidden_values(manifest: Mapping[str, Any]) -> None:
    for key, value in _walk(manifest):
        if key in _SECRET_KEYS:
            raise DeploymentPlanError(f"credential-bearing field {key} is prohibited")
        if isinstance(value, str) and value.strip().upper() in _FORBIDDEN_VALUES:
            raise DeploymentPlanError(f"forbidden replacement-credential value {value!r}")


def _validate_registry(manifest: Mapping[str, Any], manifest_path: Path) -> Path:
    raw_path = _text(manifest, "registryOutputPath")
    registry_path = Path(raw_path)
    if not registry_path.is_absolute():
        registry_path = (PROJECT_ROOT / registry_path).resolve()
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentPlanError("registry_output.json is required and must be valid JSON") from error
    if not isinstance(registry, Mapping) or not registry:
        raise DeploymentPlanError("registry_output.json must contain a non-empty object")
    if registry_path == manifest_path.resolve():
        raise DeploymentPlanError("manifest and registry output must be separate files")
    return registry_path


def _validate_protected_resources(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    resources = _records(manifest.get("protectedResources"), "protectedResources")
    dynamic = [item for item in resources if item.get("name") == "dynamic-skills-system"]
    if len(dynamic) != 1 or dynamic[0].get("mutationAllowed") is not False:
        raise DeploymentPlanError("dynamic-skills-system must be protected from mutation")
    return [
        {
            "name": _text(item, "name"),
            "mutationAllowed": item.get("mutationAllowed") is True,
        }
        for item in resources
    ]


def _validate_transport(manifest: Mapping[str, Any]) -> None:
    transport = _record(manifest.get("bearerTransport"), "bearerTransport")
    expected = {
        "bearerMode": "ORIGINAL_USER_ACCESS_JWT",
        "legacyM2mEnabled": False,
        "oauthProviderEnabled": False,
        "tokenExchangeEnabled": False,
        "contextTokenEnabled": False,
        "workloadTokenEnabled": False,
    }
    if dict(transport) != expected:
        raise DeploymentPlanError("transport must use only the original user access JWT")


def _validate_authorizers(manifest: Mapping[str, Any]) -> None:
    authorizers = _records(manifest.get("managedAuthorizers"), "managedAuthorizers")
    actual: set[tuple[str, str, str]] = set()
    for authorizer in authorizers:
        scopes = authorizer.get("allowedScopes")
        clients = authorizer.get("allowedClients")
        if not isinstance(scopes, list) or len(scopes) != 1:
            raise DeploymentPlanError("each managed authorizer must have one local scope")
        if not isinstance(clients, list) or not clients:
            raise DeploymentPlanError("each managed authorizer must have trusted clients")
        if authorizer.get("tokenUseEquals") != "access":
            raise DeploymentPlanError("each managed authorizer must require token_use EQUALS access")
        actual.add((_text(authorizer, "laneId"), _text(authorizer, "door"), scopes[0]))
    if len(authorizers) != 6 or actual != _REQUIRED_DOORS:
        raise DeploymentPlanError("exactly six same-lane managed authorizers are required")


def _validate_lanes(manifest: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], dict[str, str]]:
    lanes = _records(manifest.get("lanes"), "lanes")
    lanes_by_id = {_text(lane, "laneId"): lane for lane in lanes}
    if len(lanes) != 2 or tuple(sorted(lanes_by_id)) != _REQUIRED_LANES:
        raise DeploymentPlanError("manifest must contain exactly Tenant_A and Tenant_B")

    unique_fields = ("userPoolId", "agentRuntimeId", "gatewayId", "mcpRuntimeId", "mcpRuntimeArn")
    for lane_id, lane in lanes_by_id.items():
        if lane.get("tenantId") != lane_id:
            raise DeploymentPlanError("each lane must bind its matching tenant")
        if lane.get("candidateState") != "INACTIVE":
            raise DeploymentPlanError("all candidate lane resources must remain inactive")
        qualifier = _text(lane, "mcpRuntimeQualifier")
        if qualifier in {"DISCOVER_AFTER_INACTIVE_CREATION", "UNKNOWN", "TBD"}:
            raise DeploymentPlanError("each MCP Runtime qualifier must be approved and exact")
        rollback = _record(lane.get("rollbackTopology"), "rollbackTopology")
        for field in ("gatewayTargetId", "gatewayRoute", "agentGatewayUrl"):
            _text(rollback, field)
        target = _record(lane.get("gatewayTarget"), "gatewayTarget")
        if dict(target) != {
            "targetType": "HTTP_PASSTHROUGH",
            "protocolType": "MCP",
            "credentialProviderType": "JWT_PASSTHROUGH",
        }:
            raise DeploymentPlanError("Gateway targets must be HTTP MCP JWT_PASSTHROUGH")

    for field in unique_fields:
        values = [_text(lane, field) for lane in lanes]
        if len(set(values)) != 2:
            raise DeploymentPlanError(f"lane {field} values must be distinct")

    rollback_digests = {
        lane_id: _digest(lane["rollbackTopology"]) for lane_id, lane in lanes_by_id.items()
    }
    if len(set(rollback_digests.values())) != 2:
        raise DeploymentPlanError("independent per-lane rollback topologies are required")
    return [lanes_by_id[lane_id] for lane_id in _REQUIRED_LANES], rollback_digests


def validate_deployment_manifest(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[Path, list[Mapping[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Validate the approved identity manifest without network or file mutation."""
    if manifest.get("approvalStatus") != "APPROVED":
        raise DeploymentPlanError("manifest approvalStatus must be APPROVED")
    _text(manifest, "region")
    _validate_secret_and_forbidden_values(manifest)
    registry_path = _validate_registry(manifest, manifest_path)
    protected = _validate_protected_resources(manifest)
    _validate_transport(manifest)
    _validate_authorizers(manifest)
    lanes, rollback_digests = _validate_lanes(manifest)

    api = _record(manifest.get("sharedSageApi"), "sharedSageApi")
    _text(api, "resourceName")
    if api.get("candidateState") != "INACTIVE":
        raise DeploymentPlanError("shared Sage API candidate must remain inactive")
    if not isinstance(api.get("approvedSageMcpSourcePaths"), list) or len(api["approvedSageMcpSourcePaths"]) != 2:
        raise DeploymentPlanError("shared Sage API requires exactly two approved MCP source paths")

    frontend = _record(manifest.get("frontend"), "frontend")
    if frontend.get("deploymentAllowed") is not False:
        raise DeploymentPlanError("frontend deployment must remain prohibited before proof")

    try:
        render_deployments(dict(manifest), "agent")
        render_deployments(dict(manifest), "mcp")
        render_gateway_targets(manifest)
    except (KeyError, TypeError, ValueError) as error:
        raise DeploymentPlanError(f"identity renderer rejected manifest: {error}") from error

    return registry_path, lanes, protected, rollback_digests


def _stage(
    stage_id: str,
    category: str,
    action: str,
    *,
    lane_id: str | None = None,
    depends_on: Sequence[str] = (),
    rollback: str | None = None,
) -> dict[str, Any]:
    return {
        "id": stage_id,
        "category": category,
        "laneId": lane_id,
        "dependsOn": list(depends_on),
        "action": action,
        "requiresHumanMutationAuthorization": category == "mutation",
        "rollbackAction": rollback,
    }


def _stages(lanes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    lane_ids = [_text(lane, "laneId") for lane in lanes]
    stages = [
        _stage("01-validate", "local_generation", "validate approved manifest and render immutable candidate configuration"),
        _stage("02-inspect", "read_only", "inspect Registry, protected resources, current resources, and rollback references", depends_on=("01-validate",)),
        _stage("03-api", "mutation", "create or update the shared Sage API as an inactive candidate", depends_on=("02-inspect",), rollback="restore prior shared Sage API configuration"),
        _stage("04-api-readback", "read_only", "inspect and verify the exact inactive Sage API endpoint and source controls", depends_on=("03-api",)),
        _stage("05-mcp-patch", "local_generation", "patch both MCP candidate configurations with the exact discovered Sage API endpoint", depends_on=("04-api-readback",)),
    ]
    for lane_id in lane_ids:
        stages.append(_stage(f"06-mcp-{lane_id}", "mutation", "create or update the lane MCP Runtime as inactive", lane_id=lane_id, depends_on=("05-mcp-patch",), rollback=f"restore {lane_id} rollback topology"))
    stages.append(_stage("07-mcp-readback", "read_only", "inspect both MCP Runtime IDs, ARNs, qualifiers, and same-lane authorizers", depends_on=tuple(f"06-mcp-{lane_id}" for lane_id in lane_ids)))
    stages.append(_stage("08-gateway-patch", "local_generation", "patch Gateway targets from exact discovered same-lane MCP Runtime ARNs and qualifiers", depends_on=("07-mcp-readback",)))
    for lane_id in lane_ids:
        stages.extend(
            (
                _stage(f"09-gateway-{lane_id}", "mutation", "create or update the lane Gateway as inactive", lane_id=lane_id, depends_on=("08-gateway-patch",), rollback=f"restore {lane_id} rollback topology"),
                _stage(f"10-target-{lane_id}", "mutation", "create the lane HTTP MCP JWT_PASSTHROUGH target as inactive", lane_id=lane_id, depends_on=(f"09-gateway-{lane_id}",), rollback=f"restore {lane_id} rollback topology"),
            )
        )
    stages.append(_stage("11-target-readback", "read_only", "inspect exact target type, protocol, credential provider, endpoint, and path", depends_on=tuple(f"10-target-{lane_id}" for lane_id in lane_ids)))
    stages.append(_stage("12-agent-patch", "local_generation", "patch both Agent candidates with exact discovered target-specific Gateway URLs", depends_on=("11-target-readback",)))
    for lane_id in lane_ids:
        stages.append(_stage(f"13-agent-{lane_id}", "mutation", "create or update the lane Agent Runtime as inactive", lane_id=lane_id, depends_on=("12-agent-patch",), rollback=f"restore {lane_id} rollback topology"))
    stages.append(_stage("14-inspect-all", "read_only", "inspect exact two-lane cardinality and all six same-lane authorizers", depends_on=tuple(f"13-agent-{lane_id}" for lane_id in lane_ids)))
    for lane_id in lane_ids:
        stages.append(_stage(f"15-proof-{lane_id}", "read_only", "run every inactive lane proof gate including other-lane rejection", lane_id=lane_id, depends_on=("14-inspect-all",), rollback=f"restore {lane_id} rollback topology"))
    stages.append(_stage("16-both-lanes-gate", "gate", "permit later traffic activation only after both lane proofs pass", depends_on=tuple(f"15-proof-{lane_id}" for lane_id in lane_ids)))
    return stages


def build_dry_run(
    manifest: Mapping[str, Any],
    manifest_path: Path,
    *,
    simulated_failure: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic dry run with no AWS clients or mutations."""
    registry_path, lanes, protected, rollback_digests = validate_deployment_manifest(manifest, manifest_path)
    stages = _stages(lanes)
    stage_ids = {stage["id"] for stage in stages}
    if simulated_failure is not None and simulated_failure not in stage_ids:
        raise DeploymentPlanError("simulated failure must identify a planned stage")

    failed = False
    affected_lane: str | None = None
    for stage in stages:
        if failed:
            stage["status"] = "BLOCKED_BY_PRIOR_FAILURE"
        elif stage["id"] == simulated_failure:
            stage["status"] = "SIMULATED_FAILURE"
            failed = True
            affected_lane = stage["laneId"]
        else:
            stage["status"] = "PLANNED_NOT_EXECUTED"

    rollback_actions = [
        {
            "laneId": lane_id,
            "snapshotDigest": rollback_digests[lane_id],
            "action": f"preserve {lane_id} rollback topology unchanged",
            "selectedForSimulatedRestore": affected_lane == lane_id,
        }
        for lane_id in _REQUIRED_LANES
    ]
    return {
        "schemaVersion": "1.0",
        "mode": "DRY_RUN_LOCAL_ONLY",
        "status": "BLOCKED_BY_SIMULATED_FAILURE" if failed else "READY_FOR_TASK_13_5_REVIEW",
        "manifestDigest": _digest(manifest),
        "registryOutputPath": str(registry_path),
        "awsMutationCallsIssued": 0,
        "secretValuesIncluded": False,
        "protectedResources": protected,
        "stages": stages,
        "rollbackActions": rollback_actions,
        "failureHandling": {
            "stopOnFirstFailure": True,
            "affectedLane": affected_lane,
            "restoreOnlyAffectedLaneWhenSafe": affected_lane is not None,
            "unaffectedLaneTopologyChanged": False,
        },
        "activationGate": {
            "bothLaneProofsRequired": list(_REQUIRED_LANES),
            "trafficActivationAllowed": False,
            "frontendDeploymentAllowed": False,
            "reason": "Dry-run cannot satisfy deployed proof gates; Task 13.5 approval and later verified stages are required.",
        },
    }


def load_and_build_dry_run(
    manifest_path: Path, *, simulated_failure: str | None = None
) -> dict[str, Any]:
    """Read one manifest and return its local-only dry-run plan."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DeploymentPlanError("approved identity manifest is missing") from error
    except json.JSONDecodeError as error:
        raise DeploymentPlanError("approved identity manifest is not valid JSON") from error
    if not isinstance(manifest, Mapping):
        raise DeploymentPlanError("approved identity manifest must be an object")
    return build_dry_run(manifest, manifest_path, simulated_failure=simulated_failure)


def main() -> None:
    """Print or save a local-only dry-run plan; never invoke AWS."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--simulate-failure")
    args = parser.parse_args()

    try:
        plan = load_and_build_dry_run(args.manifest, simulated_failure=args.simulate_failure)
    except DeploymentPlanError as error:
        print(json.dumps({"status": "BLOCKED", "awsMutationCallsIssued": 0, "secretValuesIncluded": False, "error": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2) from error

    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote mutation-free dry run to {args.output}")


if __name__ == "__main__":
    main()
