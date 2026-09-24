#!/usr/bin/env python3
"""Deploy one lane's Cognito V2 access-token customizer as an immutable version.

Each tenant lane gets its own function, published version, and alias. The alias
ARN and approved ``CodeSha256`` are what ``deploy_user_pool.py`` preflight
requires, because a mutable ``$LATEST`` reference would let the customizer change
without re-approval.

The handler in ``sage_identity.cognito`` uses only the standard library, so this
package carries no third-party dependencies.

Configuration is validated locally with the same loader the Lambda uses, so an
invalid lane binding fails before any AWS call.

Usage:
  uv run python scripts/deploy_pre_token_lambda.py --lane Tenant_A \
      --user-pool-id <id> --client-id <id> --subject <sub> --render
  uv run python scripts/deploy_pre_token_lambda.py --lane Tenant_A \
      --user-pool-id <id> --client-id <id> --subject <sub>
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
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

from sage_identity import TENANT_A, TENANT_B
from sage_identity.cognito import (
    SAGE_SCOPE_PROFILE,
    load_access_token_customizer_configuration,
)
from scripts.lambda_package import build_zip

HANDLER = "sage_identity.cognito.lambda_handler"
RUNTIME = "python3.13"
ARCHITECTURE = "arm64"
TIMEOUT_SECONDS = 5
MEMORY_MB = 256
ROLE_NAME = "sage-pre-token-lambda-role"
CANONICAL_TENANT_CLAIM_NAME = "custom:tenant_id"
DEFAULT_ASSIGNMENT_ATTRIBUTE = "custom:tenant_assignment"
OUTPUT_FILE = PROJECT_ROOT / "scripts" / "pre_token_lambda_output.json"
BASIC_EXECUTION_POLICY = (
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)
_TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}


def require_qualified_lambda_arn(arn: str) -> str:
    """Require an immutable version or alias ARN, never a mutable reference.

    Cognito must be pointed at a qualified ARN so the customizer cannot change
    without re-approval. This mirrors the preflight check in
    ``scripts/deploy_user_pool.py`` and is the single guard both deployment
    stages call.

    Args:
        arn: Candidate Lambda ARN.

    Returns:
        The same ARN when it is qualified.

    Raises:
        ValueError: If the ARN is unqualified, malformed, or ``$LATEST``.
    """
    parts = arn.split(":")
    if (
        len(parts) != 8
        or parts[0] != "arn"
        or parts[2] != "lambda"
        or parts[5] != "function"
        or not parts[6]
        or not parts[7]
        or parts[7] == "$LATEST"
    ):
        raise ValueError(
            "pre-token Lambda ARN must be a qualified version or alias ARN"
        )
    return arn


def lane_suffix(lane_id: str) -> str:
    """Return the deployment name suffix for one lane."""
    return lane_id.replace("_", "-").lower()


def function_name(lane_id: str) -> str:
    """Return the per-lane customizer function name."""
    return f"sage-pre-token-{lane_suffix(lane_id)}"


def build_customizer_config(
    *,
    lane_id: str,
    user_pool_id: str,
    client_ids: list[str],
    subjects: list[str],
    assignment_attribute: str,
    scopes: list[str],
) -> str:
    """Build and locally validate one lane's customizer configuration."""
    if not client_ids or not subjects:
        raise ValueError("at least one client and one subject grant are required")
    unknown = set(scopes) - set(SAGE_SCOPE_PROFILE)
    if unknown:
        raise ValueError(f"unknown Sage scopes requested: {sorted(unknown)}")

    serialized = json.dumps(
        {
            "userPoolId": user_pool_id,
            "expectedTenant": lane_id,
            "canonicalTenantClaimName": CANONICAL_TENANT_CLAIM_NAME,
            "trustedAssignmentAttribute": assignment_attribute,
            "trustedClientIds": sorted(set(client_ids)),
            "scopeGrants": [
                {
                    "subject": subject,
                    "clientId": client_id,
                    "scopes": sorted(set(scopes)),
                }
                for client_id in sorted(set(client_ids))
                for subject in sorted(set(subjects))
            ],
        },
        sort_keys=True,
    )

    # Fail before any AWS call if the lane binding is not valid.
    load_access_token_customizer_configuration(serialized)
    return serialized


def _create_with_role_retry(lambda_client: Any, **parameters: Any) -> dict[str, Any]:
    """Create a function, tolerating IAM role propagation delay."""
    for attempt in range(10):
        try:
            return dict(lambda_client.create_function(**parameters))
        except ClientError as error:
            code = error.response["Error"]["Code"]
            message = error.response["Error"].get("Message", "")
            if (
                code != "InvalidParameterValueException"
                or "cannot be assumed" not in message
                or attempt == 9
            ):
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def ensure_role(iam: Any) -> str:
    """Create or reuse the shared customizer execution role."""
    try:
        role = iam.get_role(RoleName=ROLE_NAME)["Role"]
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
            raise
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(_TRUST_POLICY),
            Description="Execution role for Sage Cognito access-token customizers",
        )["Role"]
    iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=BASIC_EXECUTION_POLICY)
    return str(role["Arn"])


def deploy_version(
    lambda_client: Any,
    name: str,
    role_arn: str,
    package: bytes,
    serialized_config: str,
) -> tuple[str, str]:
    """Create or update the function and publish an immutable version."""
    settings = {
        "Role": role_arn,
        "Handler": HANDLER,
        "Runtime": RUNTIME,
        "Timeout": TIMEOUT_SECONDS,
        "MemorySize": MEMORY_MB,
        "Environment": {"Variables": {"SAGE_TOKEN_CUSTOMIZER_CONFIG": serialized_config}},
    }
    try:
        lambda_client.get_function(FunctionName=name)
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        _create_with_role_retry(
            lambda_client,
            FunctionName=name,
            Code={"ZipFile": package},
            Architectures=[ARCHITECTURE],
            **settings,
        )
        lambda_client.get_waiter("function_active_v2").wait(FunctionName=name)
    else:
        lambda_client.update_function_configuration(FunctionName=name, **settings)
        lambda_client.get_waiter("function_updated_v2").wait(FunctionName=name)
        lambda_client.update_function_code(FunctionName=name, ZipFile=package)
        lambda_client.get_waiter("function_updated_v2").wait(FunctionName=name)

    published = lambda_client.publish_version(FunctionName=name)
    return str(published["Version"]), str(published["CodeSha256"])


def ensure_alias(lambda_client: Any, name: str, alias: str, version: str) -> str:
    """Point the lane alias at the published version and return its ARN."""
    try:
        updated = lambda_client.update_alias(
            FunctionName=name, Name=alias, FunctionVersion=version
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        updated = lambda_client.create_alias(
            FunctionName=name, Name=alias, FunctionVersion=version
        )
    return str(updated["AliasArn"])


def allow_cognito_invoke(
    lambda_client: Any, alias_arn: str, user_pool_arn: str, statement_id: str
) -> None:
    """Permit only the lane's own user pool to invoke the alias."""
    try:
        lambda_client.add_permission(
            FunctionName=alias_arn,
            StatementId=statement_id,
            Action="lambda:InvokeFunction",
            Principal="cognito-idp.amazonaws.com",
            SourceArn=user_pool_arn,
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceConflictException":
            raise


def main() -> int:
    """Render the plan locally, or deploy one lane's immutable customizer."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--lane", choices=(TENANT_A, TENANT_B), required=True)
    parser.add_argument("--user-pool-id", required=True)
    parser.add_argument("--client-id", action="append", required=True)
    parser.add_argument("--subject", action="append", required=True)
    parser.add_argument(
        "--assignment-attribute", default=DEFAULT_ASSIGNMENT_ATTRIBUTE
    )
    parser.add_argument(
        "--scopes",
        default=",".join(sorted(SAGE_SCOPE_PROFILE)),
        help="Comma-separated Sage scopes granted to each subject and client.",
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    name = function_name(args.lane)
    alias = lane_suffix(args.lane)
    try:
        serialized_config = build_customizer_config(
            lane_id=args.lane,
            user_pool_id=args.user_pool_id,
            client_ids=list(args.client_id),
            subjects=list(args.subject),
            assignment_attribute=args.assignment_attribute,
            scopes=[scope.strip() for scope in args.scopes.split(",") if scope.strip()],
        )
    except ValueError as error:
        print(f"Customizer configuration rejected: {error}", file=sys.stderr)
        return 1

    if args.render:
        print(
            json.dumps(
                {
                    "functionName": name,
                    "alias": alias,
                    "handler": HANDLER,
                    "runtime": RUNTIME,
                    "architecture": ARCHITECTURE,
                    "region": args.region,
                    "bundledDependencies": [],
                    "customizerConfig": json.loads(serialized_config),
                    "awsMutationCallsIssued": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    iam = boto3.client("iam")
    lambda_client = boto3.client("lambda", region_name=args.region)
    cognito = boto3.client("cognito-idp", region_name=args.region)

    pool = cognito.describe_user_pool(UserPoolId=args.user_pool_id)["UserPool"]
    user_pool_arn = pool.get("Arn")
    if not isinstance(user_pool_arn, str) or not user_pool_arn:
        print("User pool ARN could not be read", file=sys.stderr)
        return 1

    role_arn = ensure_role(iam)
    package = build_zip(("sage_identity",), ())
    version, code_sha256 = deploy_version(
        lambda_client, name, role_arn, package, serialized_config
    )
    alias_arn = ensure_alias(lambda_client, name, alias, version)
    allow_cognito_invoke(
        lambda_client, alias_arn, user_pool_arn, f"CognitoInvoke-{args.user_pool_id}"
    )

    record = {
        "laneId": args.lane,
        "region": args.region,
        "functionName": name,
        "alias": alias,
        "publishedVersion": version,
        "aliasArn": alias_arn,
        "codeSha256": code_sha256,
        "userPoolId": args.user_pool_id,
        "trustedAssignmentAttribute": args.assignment_attribute,
    }
    existing = (
        json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        if OUTPUT_FILE.exists()
        else {}
    )
    existing[args.lane] = record
    OUTPUT_FILE.write_text(
        json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    prefix = args.lane.upper()
    print(f"Deployed {name} version {version}; wrote {OUTPUT_FILE}")
    print(f"{prefix}_PRE_TOKEN_LAMBDA_ARN={alias_arn}")
    print(f"{prefix}_PRE_TOKEN_LAMBDA_CODE_SHA256={code_sha256}")
    print(f"{prefix}_TRUSTED_ASSIGNMENT_ATTRIBUTE={args.assignment_attribute}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
