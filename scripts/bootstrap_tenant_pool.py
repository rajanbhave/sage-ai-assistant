#!/usr/bin/env python3
"""Create one tenant lane's Cognito pool, public client, and demo subject.

``deploy_user_pool.py`` configures pools that already exist and requires an
active ``V2_0`` customizer before it will touch anything. This script creates the
prerequisites it assumes, in the only order the dependencies permit:

    create        pool, trusted assignment attribute, public client, demo user
    attach-trigger  point the pool's V2_0 PreTokenGeneration at the lane alias

The customizer configuration must name the client and the subject, and both are
created here, so the alias cannot exist until ``create`` has run. That is why
trigger attachment is a separate command rather than part of ``create``.

The canonical ``custom:tenant_id`` claim is deliberately NOT a pool attribute. It
is emitted only by the customizer as an access-token claim, so no client or user
can write the value that the managed authorizers match on. The pool holds only
the administratively controlled assignment attribute.

Demo passwords are read from ``<LANE>_DEMO_PASSWORD`` and are never logged,
echoed, or written to output.

Usage:
  uv run python scripts/bootstrap_tenant_pool.py create --lane Tenant_A --render
  TENANT_A_DEMO_PASSWORD=... uv run python scripts/bootstrap_tenant_pool.py \
      create --lane Tenant_A --username axa-user --confirm
  uv run python scripts/bootstrap_tenant_pool.py attach-trigger --lane Tenant_A \
      --lambda-arn <alias-arn> --confirm
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
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
from scripts.deploy_pre_token_lambda import require_qualified_lambda_arn

ASSIGNMENT_ATTRIBUTE = "custom:tenant_assignment"
ASSIGNMENT_ATTRIBUTE_NAME = "tenant_assignment"
FEATURE_PLAN = "ESSENTIALS"
PUBLIC_AUTH_FLOWS = (
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
)
DEFAULT_ACCESS_TOKEN_VALIDITY = 60
DEFAULT_ACCESS_TOKEN_VALIDITY_UNIT = "minutes"
OUTPUT_FILE = PROJECT_ROOT / "scripts" / "tenant_pool_bootstrap.json"

# Phase 1 resources that must never be reused or mutated by this script.
PROTECTED_POOL_NAMES = frozenset({"sage-tenant-pool", "sage-mcp-pool"})

# UpdateUserPool replaces omitted settings with defaults, so these are read back
# and resent whenever the trigger is attached.
_PRESERVED_POOL_KEYS = (
    "Policies",
    "DeletionProtection",
    "AutoVerifiedAttributes",
    "VerificationMessageTemplate",
    "MfaConfiguration",
    "UserAttributeUpdateSettings",
    "DeviceConfiguration",
    "EmailConfiguration",
    "SmsConfiguration",
    "UserPoolTags",
    "AdminCreateUserConfig",
    "UserPoolAddOns",
    "AccountRecoverySetting",
    "UserPoolTier",
)


def lane_suffix(lane_id: str) -> str:
    """Return the deployment name suffix for one lane."""
    return lane_id.replace("_", "-").lower()


def pool_name(lane_id: str) -> str:
    """Return the lane's pool name, distinct from every Phase 1 name."""
    return f"sage-{lane_suffix(lane_id)}-pool"


def client_name(lane_id: str) -> str:
    """Return the lane's public client name expected by deploy_user_pool."""
    return f"sage-tenant-{lane_id[-1].lower()}-client"


def _find_pool(cognito: Any, name: str) -> str | None:
    paginator = cognito.get_paginator("list_user_pools")
    matches = [
        pool["Id"]
        for page in paginator.paginate(MaxResults=60)
        for pool in page.get("UserPools", [])
        if pool.get("Name") == name
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple pools are named {name}")
    return matches[0] if matches else None


def _verify_adopted_pool(cognito: Any, pool_id: str, name: str) -> None:
    """Require an already-existing lane pool to match what create would build.

    Re-running this command must not silently adopt a pool that cannot support
    the V2_0 customizer, because the failure would otherwise surface two stages
    later at trigger attachment or first sign-in.
    """
    pool = cognito.describe_user_pool(UserPoolId=pool_id)["UserPool"]
    tier = pool.get("UserPoolTier")
    if tier != FEATURE_PLAN:
        raise ValueError(
            f"{name} is on feature plan {tier!r}; {FEATURE_PLAN} is required for V2_0"
        )
    assignment = [
        attribute
        for attribute in pool.get("SchemaAttributes", [])
        if attribute.get("Name") == ASSIGNMENT_ATTRIBUTE
        and attribute.get("AttributeDataType") == "String"
    ]
    if len(assignment) != 1:
        raise ValueError(
            f"{name} must have exactly one {ASSIGNMENT_ATTRIBUTE} string attribute"
        )


def create_pool(cognito: Any, lane_id: str) -> str:
    """Create the lane pool with exactly one trusted assignment attribute."""
    name = pool_name(lane_id)
    if name in PROTECTED_POOL_NAMES:
        raise ValueError(f"{name} is a protected Phase 1 pool")

    existing = _find_pool(cognito, name)
    if existing is not None:
        _verify_adopted_pool(cognito, existing, name)
        return existing

    created = cognito.create_user_pool(
        PoolName=name,
        UserPoolTier=FEATURE_PLAN,
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 12,
                "RequireUppercase": True,
                "RequireLowercase": True,
                "RequireNumbers": True,
                "RequireSymbols": True,
            }
        },
        Schema=[
            {
                "Name": ASSIGNMENT_ATTRIBUTE_NAME,
                "AttributeDataType": "String",
                "Mutable": True,
                "Required": False,
                "DeveloperOnlyAttribute": False,
                "StringAttributeConstraints": {
                    "MinLength": "1",
                    "MaxLength": "32",
                },
            }
        ],
        AdminCreateUserConfig={"AllowAdminCreateUserOnly": True},
        MfaConfiguration="OFF",
        DeletionProtection="INACTIVE",
    )
    return str(created["UserPool"]["Id"])


def create_public_client(
    cognito: Any,
    pool_id: str,
    lane_id: str,
    access_token_validity: int,
    access_token_validity_unit: str,
) -> str:
    """Create the one public browser client deploy_user_pool will verify.

    The assignment attribute is readable but never writable, so the browser
    cannot change the value the customizer trusts.
    """
    name = client_name(lane_id)
    existing = [
        client["ClientId"]
        for page in cognito.get_paginator("list_user_pool_clients").paginate(
            UserPoolId=pool_id
        )
        for client in page.get("UserPoolClients", [])
        if client.get("ClientName") == name
    ]
    if len(existing) > 1:
        raise ValueError(f"{lane_id} has duplicate public clients named {name}")
    if existing:
        return existing[0]

    created = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=name,
        GenerateSecret=False,
        ExplicitAuthFlows=list(PUBLIC_AUTH_FLOWS),
        ReadAttributes=[ASSIGNMENT_ATTRIBUTE],
        WriteAttributes=[],
        AccessTokenValidity=access_token_validity,
        TokenValidityUnits={"AccessToken": access_token_validity_unit},
        PreventUserExistenceErrors="ENABLED",
        EnableTokenRevocation=True,
    )
    return str(created["UserPoolClient"]["ClientId"])


def create_demo_subject(
    cognito: Any, pool_id: str, lane_id: str, username: str, password: str
) -> str:
    """Create or reuse the demo user and return its immutable subject."""
    try:
        user = cognito.admin_get_user(UserPoolId=pool_id, Username=username)
    except cognito.exceptions.UserNotFoundException:
        user = cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=username,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": ASSIGNMENT_ATTRIBUTE, "Value": lane_id},
            ],
        )["User"]
    else:
        cognito.admin_update_user_attributes(
            UserPoolId=pool_id,
            Username=username,
            UserAttributes=[{"Name": ASSIGNMENT_ATTRIBUTE, "Value": lane_id}],
        )

    cognito.admin_set_user_password(
        UserPoolId=pool_id, Username=username, Password=password, Permanent=True
    )

    attributes = user.get("Attributes") or user.get("UserAttributes") or []
    subjects = [
        attribute["Value"]
        for attribute in attributes
        if attribute.get("Name") == "sub" and attribute.get("Value")
    ]
    if len(subjects) != 1:
        refreshed = cognito.admin_get_user(UserPoolId=pool_id, Username=username)
        subjects = [
            attribute["Value"]
            for attribute in refreshed.get("UserAttributes", [])
            if attribute.get("Name") == "sub" and attribute.get("Value")
        ]
    if len(subjects) != 1:
        raise ValueError(f"{lane_id} demo user has no single subject claim")
    return subjects[0]


def attach_pre_token_trigger(cognito: Any, pool_id: str, alias_arn: str) -> None:
    """Attach the V2_0 customizer, preserving every other pool setting.

    UpdateUserPool resets omitted settings to their defaults, so the current
    configuration is read back and resent with only LambdaConfig changed.
    """
    require_qualified_lambda_arn(alias_arn)

    pool = cognito.describe_user_pool(UserPoolId=pool_id)["UserPool"]
    if pool.get("Name") in PROTECTED_POOL_NAMES:
        raise ValueError("refusing to modify a protected Phase 1 pool")

    lambda_config = dict(pool.get("LambdaConfig") or {})
    lambda_config["PreTokenGenerationConfig"] = {
        "LambdaVersion": "V2_0",
        "LambdaArn": alias_arn,
    }
    # The legacy single-version field must agree when it is present.
    if "PreTokenGeneration" in lambda_config:
        lambda_config["PreTokenGeneration"] = alias_arn

    parameters: dict[str, Any] = {
        "UserPoolId": pool_id,
        "LambdaConfig": lambda_config,
    }
    for key in _PRESERVED_POOL_KEYS:
        if key in pool:
            parameters[key] = pool[key]

    cognito.update_user_pool(**parameters)

    updated = cognito.describe_user_pool(UserPoolId=pool_id)["UserPool"]
    trigger = (updated.get("LambdaConfig") or {}).get(
        "PreTokenGenerationConfig", {}
    )
    if (
        trigger.get("LambdaVersion") != "V2_0"
        or trigger.get("LambdaArn") != alias_arn
    ):
        raise ValueError("V2_0 customizer readback does not match the lane alias")


def _load_output() -> dict[str, Any]:
    if not OUTPUT_FILE.exists():
        return {}
    return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))


def _save_output(lane_id: str, record: dict[str, Any]) -> None:
    existing = _load_output()
    existing[lane_id] = {**existing.get(lane_id, {}), **record}
    OUTPUT_FILE.write_text(
        json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _issuer(region: str, pool_id: str) -> str:
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"


def run_create(args: argparse.Namespace) -> int:
    """Create the lane pool, client, and demo subject."""
    prefix = args.lane.upper()
    plan = {
        "command": "create",
        "laneId": args.lane,
        "region": args.region,
        "poolName": pool_name(args.lane),
        "featurePlan": FEATURE_PLAN,
        "clientName": client_name(args.lane),
        "trustedAssignmentAttribute": ASSIGNMENT_ATTRIBUTE,
        "canonicalClaimIsPoolAttribute": False,
        "username": args.username,
        "accessTokenValidity": args.access_token_validity,
        "accessTokenValidityUnit": args.access_token_validity_unit,
        "publicAuthFlows": list(PUBLIC_AUTH_FLOWS),
        "assignmentAttributeWritableByClient": False,
        "awsMutationCallsIssued": 0,
    }

    if args.render:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    password = os.environ.get(f"{prefix}_DEMO_PASSWORD", "")
    if not password.strip():
        print(
            f"Set {prefix}_DEMO_PASSWORD before creating the demo user.",
            file=sys.stderr,
        )
        return 1
    if not args.confirm:
        print(
            "Refusing to create Cognito resources without --confirm.",
            file=sys.stderr,
        )
        return 1

    cognito = boto3.client("cognito-idp", region_name=args.region)
    pool_id = create_pool(cognito, args.lane)
    client_id = create_public_client(
        cognito,
        pool_id,
        args.lane,
        args.access_token_validity,
        args.access_token_validity_unit,
    )
    subject = create_demo_subject(
        cognito, pool_id, args.lane, args.username, password
    )

    issuer = _issuer(args.region, pool_id)
    _save_output(
        args.lane,
        {
            "laneId": args.lane,
            "region": args.region,
            "userPoolId": pool_id,
            "poolName": pool_name(args.lane),
            "clientId": client_id,
            "clientName": client_name(args.lane),
            "username": args.username,
            "subject": subject,
            "issuer": issuer,
            "discoveryUrl": f"{issuer}/.well-known/openid-configuration",
            "trustedAssignmentAttribute": ASSIGNMENT_ATTRIBUTE,
            "approvedAccessTokenValidity": args.access_token_validity,
            "approvedAccessTokenValidityUnit": args.access_token_validity_unit,
        },
    )
    print(f"Created {pool_name(args.lane)}; wrote {OUTPUT_FILE}")
    print(f"{prefix}_USER_POOL_ID={pool_id}")
    print(f"{prefix}_CLIENT_ID={client_id}")
    print(f"{prefix}_SUBJECT={subject}")
    return 0


def run_attach_trigger(args: argparse.Namespace) -> int:
    """Attach the lane's published customizer alias as the V2_0 trigger."""
    record = _load_output().get(args.lane, {})
    pool_id = args.user_pool_id or record.get("userPoolId")
    if not pool_id:
        print(
            "Run create first, or pass --user-pool-id explicitly.",
            file=sys.stderr,
        )
        return 1

    if args.render:
        print(
            json.dumps(
                {
                    "command": "attach-trigger",
                    "laneId": args.lane,
                    "userPoolId": pool_id,
                    "lambdaVersion": "V2_0",
                    "lambdaArn": args.lambda_arn,
                    "preservedPoolSettings": list(_PRESERVED_POOL_KEYS),
                    "awsMutationCallsIssued": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.confirm:
        print("Refusing to modify the pool without --confirm.", file=sys.stderr)
        return 1

    cognito = boto3.client("cognito-idp", region_name=args.region)
    attach_pre_token_trigger(cognito, pool_id, args.lambda_arn)
    _save_output(
        args.lane,
        {"preTokenLambdaArn": args.lambda_arn, "preTokenLambdaVersion": "V2_0"},
    )
    print(f"Attached V2_0 customizer to {pool_id}")
    return 0


def main() -> int:
    """Render or apply one bootstrap stage for a single tenant lane."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--region", default="us-east-1")
    create.add_argument("--lane", choices=(TENANT_A, TENANT_B), required=True)
    create.add_argument("--username", required=True)
    create.add_argument(
        "--access-token-validity", type=int, default=DEFAULT_ACCESS_TOKEN_VALIDITY
    )
    create.add_argument(
        "--access-token-validity-unit",
        default=DEFAULT_ACCESS_TOKEN_VALIDITY_UNIT,
        choices=("seconds", "minutes", "hours", "days"),
    )
    create.add_argument("--render", action="store_true")
    create.add_argument("--confirm", action="store_true")
    create.set_defaults(handler=run_create)

    attach = subparsers.add_parser("attach-trigger")
    attach.add_argument("--region", default="us-east-1")
    attach.add_argument("--lane", choices=(TENANT_A, TENANT_B), required=True)
    attach.add_argument("--lambda-arn", required=True)
    attach.add_argument("--user-pool-id")
    attach.add_argument("--render", action="store_true")
    attach.add_argument("--confirm", action="store_true")
    attach.set_defaults(handler=run_attach_trigger)

    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (ValueError, OSError) as error:
        print(f"Bootstrap rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
