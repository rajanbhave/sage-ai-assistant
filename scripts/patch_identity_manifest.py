#!/usr/bin/env python3
"""Replace provisional manifest values with live deployed readbacks.

The manifest must be authored before the MCP Runtimes, Gateway targets, and
Agent Runtimes exist, so several lane fields start as lane-distinct provisional
placeholders. Left unpatched they make ``plan_identity_deployment.py`` validate
values that are not true, which is worse than a missing field because the
validation appears to pass.

This command reads deployed state and rewrites only those fields:

- ``mcpRuntimeArn`` and ``mcpRuntimeQualifier`` from the deployed MCP Runtime
- ``gatewayTargetUrl`` from the deployed Gateway target
- ``agentRuntimeEndpoint`` from the deployed Agent Runtime

Anything it cannot resolve is reported and left unchanged, so a partial
deployment never produces a manifest that overstates reality.

Usage:
  uv run python scripts/patch_identity_manifest.py --render
  uv run python scripts/patch_identity_manifest.py --write
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.parse
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

from sage_identity import TENANT_A, TENANT_B

DEFAULT_MANIFEST = PROJECT_ROOT / "scripts" / "identity_deployment.json"
PROVISIONAL_MARKERS = (".invalid", "-patched", "provisional")


def _is_provisional(value: object) -> bool:
    return isinstance(value, str) and any(
        marker in value for marker in PROVISIONAL_MARKERS
    )


def _runtime_invocation_url(region: str, runtime_arn: str, qualifier: str) -> str:
    encoded_arn = urllib.parse.quote(runtime_arn, safe="")
    encoded_qualifier = urllib.parse.quote(qualifier, safe="")
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
        f"{encoded_arn}/invocations?qualifier={encoded_qualifier}"
    )


def _runtimes_by_name(agentcore: Any) -> dict[str, dict[str, Any]]:
    return {
        runtime["agentRuntimeName"]: runtime
        for runtime in agentcore.list_agent_runtimes(maxResults=100).get(
            "agentRuntimes", []
        )
        if runtime.get("agentRuntimeName")
    }


def _gateway_target_url(agentcore: Any, gateway_id: str, lane_id: str) -> str | None:
    """Resolve the Gateway-side MCP URL the Agent should call for this lane.

    HTTP passthrough targets use path-based routing, where the gateway forwards
    ``/{targetName}/{path}`` to ``{endpoint}/{path}``. The target endpoint is the
    MCP Runtime base URL, so the path must be ``invocations`` to produce the
    Runtime's own invocation URL:
    ``https://{gatewayId}.gateway.bedrock-agentcore.{region}.amazonaws.com/{targetName}/invocations``
    This is the Agent's ``GATEWAY_URL``, which is distinct from the target's own
    endpoint (the MCP Runtime base URL).
    """
    gateway = agentcore.get_gateway(gatewayIdentifier=gateway_id)
    base = gateway.get("gatewayUrl")
    if not isinstance(base, str) or not base:
        return None
    expected = f"sage-mcp-{lane_id.replace('_', '-').lower()}"
    names = [
        target.get("name")
        for target in agentcore.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=20
        ).get("items", [])
        if target.get("name") == expected and target.get("status") == "READY"
    ]
    if not names:
        return None
    return f"{base.rstrip('/')}/{expected}/invocations"


def resolve_lane_patches(
    manifest: dict[str, Any], agentcore: Any
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Resolve replacement values for every provisional lane field."""
    region = str(manifest["region"])
    runtimes = _runtimes_by_name(agentcore)
    patches: dict[str, dict[str, str]] = {}
    unresolved: list[str] = []

    for lane in manifest.get("lanes", []):
        lane_id = str(lane.get("laneId"))
        lane_patch: dict[str, str] = {}

        mcp = runtimes.get(str(lane.get("mcpRuntimeId")))
        if mcp is None:
            unresolved.append(f"{lane_id}: MCP Runtime not deployed")
        else:
            lane_patch["mcpRuntimeArn"] = str(mcp["agentRuntimeArn"])
            lane_patch["mcpRuntimeQualifier"] = "DEFAULT"

        target_url = _gateway_target_url(
            agentcore, str(lane.get("gatewayId")), lane_id
        )
        if target_url is None:
            unresolved.append(f"{lane_id}: Gateway target not READY")
        else:
            lane_patch["gatewayTargetUrl"] = target_url

        agent = runtimes.get(str(lane.get("agentRuntimeId")))
        if agent is None:
            unresolved.append(f"{lane_id}: Agent Runtime not deployed")
        else:
            agent_endpoints = agentcore.list_agent_runtime_endpoints(
                agentRuntimeId=str(agent["agentRuntimeId"]), maxResults=20
            ).get("runtimeEndpoints", [])
            ready = [
                endpoint
                for endpoint in agent_endpoints
                if endpoint.get("status") == "READY" and endpoint.get("name")
            ]
            qualifier = str(ready[0]["name"]) if ready else "DEFAULT"
            lane_patch["agentRuntimeEndpoint"] = _runtime_invocation_url(
                region, str(agent["agentRuntimeArn"]), qualifier
            )

        if lane_patch:
            patches[lane_id] = lane_patch

    return patches, unresolved


def apply_patches(
    manifest: dict[str, Any], patches: dict[str, dict[str, str]]
) -> list[str]:
    """Apply resolved values and report each field that changed."""
    changes: list[str] = []
    for lane in manifest.get("lanes", []):
        lane_patch = patches.get(str(lane.get("laneId")), {})
        for field, value in lane_patch.items():
            if lane.get(field) != value:
                marker = " (was provisional)" if _is_provisional(lane.get(field)) else ""
                changes.append(f"{lane['laneId']}.{field}{marker}")
                lane[field] = value
    return changes


def remaining_provisional(manifest: dict[str, Any]) -> list[str]:
    """List every lane field still holding a provisional value."""
    return [
        f"{lane.get('laneId')}.{field}"
        for lane in manifest.get("lanes", [])
        for field, value in lane.items()
        if _is_provisional(value)
    ]


def main() -> int:
    """Report or apply manifest patches from live deployed state."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    agentcore = boto3.client(
        "bedrock-agentcore-control", region_name=str(manifest["region"])
    )
    patches, unresolved = resolve_lane_patches(manifest, agentcore)

    if args.render or not args.write:
        print(
            json.dumps(
                {
                    "resolvedPatches": patches,
                    "unresolved": unresolved,
                    "stillProvisional": remaining_provisional(manifest),
                    "manifestWritten": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    changes = apply_patches(manifest, patches)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "patchedFields": changes,
                "unresolved": unresolved,
                "stillProvisional": remaining_provisional(manifest),
                "manifestWritten": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
