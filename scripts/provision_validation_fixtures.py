#!/usr/bin/env python3
"""Provision the negative-path fixtures that scripts/validate_route_c.py needs.

Two live checks cannot run without deliberately weakened identities:

- **unapproved app client** — a second public app client in the lane pool that is
  absent from every managed authorizer's ``allowedClients``. A token it issues is
  cryptographically valid, carries the right issuer and tenant claim, and must
  still be rejected at every door.
- **missing-scope canaries** — one user per managed door whose customizer scope
  grant omits exactly that door's scope. Each proves the door reads
  ``allowedScopes`` rather than accepting any valid same-lane token.

Both are weakened on purpose, so they are created only under ``--confirm`` and
only in the lane pools named in the manifest. ``--render`` describes the plan and
issues no AWS call.

The canary grants themselves live in the pre-token customizer configuration, not
here: this script creates the users and prints the ``scopeGrants`` entries to add
to each lane's ``SAGE_TOKEN_CUSTOMIZER_CONFIG``. Without that edit a canary user
gets no scopes at all and the check would pass for the wrong reason.

Usage:
  uv run python scripts/provision_validation_fixtures.py --render
  uv run python scripts/provision_validation_fixtures.py --confirm
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
from collections.abc import Mapping
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

DEFAULT_MANIFEST = PROJECT_ROOT / "scripts" / "identity_deployment.json"
DEFAULT_FIXTURES = PROJECT_ROOT / "scripts" / "demo_credentials.local.json"
UNAPPROVED_CLIENT_SUFFIX = "unapproved-client"
CANARY_DOORS: tuple[str, ...] = ("agent_runtime", "gateway", "mcp_runtime")
DOOR_SCOPE = {
    "agent_runtime": "sage-agent/invoke",
    "gateway": "sage-gateway/invoke",
    "mcp_runtime": "sage-mcp/invoke",
}
ALL_SCOPES = (
    "sage-agent/invoke",
    "sage-gateway/invoke",
    "sage-mcp/invoke",
    "sage-api/read",
)
AUTH_FLOWS = ("ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH")


def lane_records(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(lane["laneId"]): dict(lane) for lane in manifest["lanes"]}


def canary_username(lane_id: str, door: str) -> str:
    return f"canary-{lane_id.replace('_', '-').lower()}-{door.replace('_', '-')}"


def canary_scopes(door: str) -> list[str]:
    """Every Sage scope except the one the door under test requires."""
    return [scope for scope in ALL_SCOPES if scope != DOOR_SCOPE[door]]


def plan(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Describe every fixture without calling AWS."""
    lanes = lane_records(manifest)
    return {
        "awsMutationCallsIssued": 0,
        "lanes": [
            {
                "laneId": lane_id,
                "userPoolId": lane["userPoolId"],
                "unapprovedClientName": (
                    f"sage-{lane_id.replace('_', '-').lower()}-"
                    f"{UNAPPROVED_CLIENT_SUFFIX}"
                ),
                "unapprovedClientNote": (
                    "must NOT be added to any managed authorizer allowedClients"
                ),
                "canaryUsers": [
                    {
                        "door": door,
                        "username": canary_username(lane_id, door),
                        "omittedScope": DOOR_SCOPE[door],
                        "customizerScopeGrant": {
                            "subject": "<the created user's sub>",
                            "clientId": lane["frontendClientIds"][0],
                            "scopes": canary_scopes(door),
                        },
                    }
                    for door in CANARY_DOORS
                ],
            }
            for lane_id, lane in sorted(lanes.items())
        ],
        "followUp": (
            "Add each customizerScopeGrant to that lane's "
            "SAGE_TOKEN_CUSTOMIZER_CONFIG scopeGrants, then redeploy the "
            "customizer. Until then a canary receives no scopes."
        ),
    }


def create_unapproved_client(cognito: Any, lane_id: str, pool_id: str) -> str:
    """Create a public client that no managed authorizer trusts."""
    name = f"sage-{lane_id.replace('_', '-').lower()}-{UNAPPROVED_CLIENT_SUFFIX}"
    existing = [
        client
        for page in cognito.get_paginator("list_user_pool_clients").paginate(
            UserPoolId=pool_id
        )
        for client in page["UserPoolClients"]
        if client["ClientName"] == name
    ]
    if existing:
        return str(existing[0]["ClientId"])
    created = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=name,
        GenerateSecret=False,
        ExplicitAuthFlows=list(AUTH_FLOWS),
    )
    return str(created["UserPoolClient"]["ClientId"])


def create_canary_user(
    cognito: Any, pool_id: str, username: str, assignment_attribute: str, tenant: str
) -> str:
    """Create one canary user with a generated password, returned to the caller."""
    password = f"Cy-{secrets.token_urlsafe(18)}"
    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=username,
            MessageAction="SUPPRESS",
            UserAttributes=[{"Name": assignment_attribute, "Value": tenant}],
        )
    except cognito.exceptions.UsernameExistsException:
        pass
    cognito.admin_set_user_password(
        UserPoolId=pool_id, Username=username, Password=password, Permanent=True
    )
    return password


def provision(cognito: Any, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Create the fixtures and return the block to merge into the fixtures file."""
    assignment_attribute = os.environ.get(
        "SAGE_ASSIGNMENT_ATTRIBUTE", "custom:tenant_assignment"
    )
    result: dict[str, Any] = {}
    for lane_id, lane in sorted(lane_records(manifest).items()):
        pool_id = str(lane["userPoolId"])
        entry: dict[str, Any] = {
            "unapprovedClientId": create_unapproved_client(cognito, lane_id, pool_id),
            "canaryUsers": {},
        }
        for door in CANARY_DOORS:
            username = canary_username(lane_id, door)
            entry["canaryUsers"][door] = {
                "username": username,
                "password": create_canary_user(
                    cognito, pool_id, username, assignment_attribute, lane_id
                ),
            }
        result[lane_id] = entry
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--render", action="store_true", help="Print the plan; call no AWS API."
    )
    parser.add_argument(
        "--confirm", action="store_true", help="Required to create the fixtures."
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES,
        help="Gitignored file the new block is merged into under --confirm.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.render or not args.confirm:
        print(json.dumps(plan(manifest), indent=2, sort_keys=True))
        if not args.render:
            print("Refusing to create fixtures without --confirm.", file=sys.stderr)
            return 1
        return 0

    region = str(manifest["region"])
    cognito = boto3.client("cognito-idp", region_name=region)
    provisioned = provision(cognito, manifest)

    existing = (
        json.loads(args.fixtures.read_text(encoding="utf-8"))
        if args.fixtures.exists()
        else {}
    )
    for lane_id, entry in provisioned.items():
        existing.setdefault(lane_id, {}).update(entry)
    args.fixtures.write_text(
        json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.fixtures.chmod(0o600)

    # Passwords are written to the gitignored fixtures file, never printed.
    print(f"Provisioned validation fixtures -> {args.fixtures}")
    print(
        "Add the printed customizerScopeGrant entries "
        "(--render) to each lane's SAGE_TOKEN_CUSTOMIZER_CONFIG, "
        "then redeploy the customizer."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
