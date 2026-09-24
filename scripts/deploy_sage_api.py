#!/usr/bin/env python3
"""Deploy the single shared Sage API boundary behind an API Gateway HTTP API.

The Sage API owns independent JWT validation, subject and tenant authorization,
and tenant data isolation. This script creates or updates exactly one function
plus its HTTP API route, and writes non-secret deployment output for later stages.

Issuer configuration is derived from the two deployed Cognito pools: the script
reads each pool's published JWKS, which contains only public keys.

Public endpoint exposure
------------------------
The MCP Runtime calls this API with the original user access token, not SigV4,
so the HTTP API carries no gateway-level authorizer and the endpoint is reachable
from the internet. Authorization rests entirely on the API's own validation: RS256
signature against the pool's published keys, issuer, expiry, trusted client,
``token_use``, the ``sage-api/read`` scope, and the exact tenant claim. Because
a public endpoint has no trusted private ingress, the request source control is
deployment-asserted and must be recorded as unavailable. Reserved concurrency
bounds abuse and cost. Deploying the public endpoint requires --allow-public-url.

A Lambda Function URL is no longer created. ``remove_blocked_function_url``
deletes one left behind by an earlier deployment, because organization policy
blocks it and a stale URL would be a second, unaudited way in.

Usage:
  uv run python scripts/deploy_sage_api.py --lane-a-pool-id <id> \
      --lane-a-client-id <id> --lane-b-pool-id <id> --lane-b-client-id <id> --render
  uv run python scripts/deploy_sage_api.py ... --allow-public-url
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.request
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
from scripts.lambda_package import build_zip

FUNCTION_NAME = "sage-api"
HTTP_API_NAME = "sage-api-http"
ROLE_NAME = "sage-api-lambda-role"
HANDLER = "sage_api.lambda_handler.lambda_handler"
RUNTIME = "python3.13"
ARCHITECTURE = "arm64"
TIMEOUT_SECONDS = 15
MEMORY_MB = 512
RESERVED_CONCURRENCY = 5
SOURCE_PATH = "sage-mcp-runtime"
OUTPUT_FILE = PROJECT_ROOT / "scripts" / "sage_api_output.json"
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


def issuer_url(region: str, pool_id: str) -> str:
    """Return the exact Cognito issuer URL for one user pool."""
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"


def fetch_jwks(region: str, pool_id: str) -> dict[str, Any]:
    """Read one pool's published public signing keys."""
    url = f"{issuer_url(region, pool_id)}/.well-known/jwks.json"
    with urllib.request.urlopen(url, timeout=15) as response:
        document = json.load(response)
    keys = document.get("keys") if isinstance(document, dict) else None
    if not isinstance(keys, list) or not keys:
        raise ValueError(f"pool {pool_id} published no usable signing keys")
    if any("d" in key for key in keys if isinstance(key, dict)):
        raise ValueError("JWKS unexpectedly contained private key material")
    return document


def build_configuration(
    region: str, lanes: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Build the non-secret environment for the shared Sage API."""
    if set(lanes) != {TENANT_A, TENANT_B}:
        raise ValueError("exactly Tenant_A and Tenant_B must be configured")

    issuer_map = []
    public_keys = {}
    for tenant_id in (TENANT_A, TENANT_B):
        lane = lanes[tenant_id]
        issuer = issuer_url(region, lane["poolId"])
        issuer_map.append(
            {
                "issuer": issuer,
                "discovery_url": f"{issuer}/.well-known/openid-configuration",
                "expected_tenant_id": tenant_id,
                "trusted_client_ids": [lane["clientId"]],
            }
        )
        public_keys[issuer] = fetch_jwks(region, lane["poolId"])

    if len({entry["issuer"] for entry in issuer_map}) != 2:
        raise ValueError("each lane requires its own distinct Cognito pool")

    return {
        "SAGE_API_ISSUER_MAP": json.dumps(issuer_map, sort_keys=True),
        "SAGE_API_PUBLIC_KEYS": json.dumps(public_keys, sort_keys=True),
        "SAGE_API_APPROVED_SOURCES": SOURCE_PATH,
        "SAGE_API_SOURCE_PATH": SOURCE_PATH,
    }


def ensure_role(iam: Any) -> str:
    """Create or reuse the least-privilege execution role for this function."""
    try:
        role = iam.get_role(RoleName=ROLE_NAME)["Role"]
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
            raise
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(_TRUST_POLICY),
            Description="Execution role for the shared Sage API boundary",
        )["Role"]
    iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=BASIC_EXECUTION_POLICY)
    return str(role["Arn"])


def _create_with_role_retry(lambda_client: Any, **parameters: Any) -> dict[str, Any]:
    """Create a function, tolerating IAM role propagation delay.

    A freshly created role is not immediately assumable, which surfaces as
    InvalidParameterValueException on a first-ever deploy.
    """
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


def deploy_function(
    lambda_client: Any, role_arn: str, package: bytes, environment: dict[str, str]
) -> str:
    """Create or update exactly one Sage API function and return its ARN."""
    settings = {
        "Role": role_arn,
        "Handler": HANDLER,
        "Runtime": RUNTIME,
        "Timeout": TIMEOUT_SECONDS,
        "MemorySize": MEMORY_MB,
        "Environment": {"Variables": environment},
    }
    try:
        lambda_client.get_function(FunctionName=FUNCTION_NAME)
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        created = _create_with_role_retry(
            lambda_client,
            FunctionName=FUNCTION_NAME,
            Code={"ZipFile": package},
            Architectures=[ARCHITECTURE],
            Publish=True,
            **settings,
        )
        lambda_client.get_waiter("function_active_v2").wait(
            FunctionName=FUNCTION_NAME
        )
        return str(created["FunctionArn"])

    lambda_client.update_function_configuration(
        FunctionName=FUNCTION_NAME, **settings
    )
    lambda_client.get_waiter("function_updated_v2").wait(
        FunctionName=FUNCTION_NAME
    )
    updated = lambda_client.update_function_code(
        FunctionName=FUNCTION_NAME, ZipFile=package, Publish=True
    )
    lambda_client.get_waiter("function_updated_v2").wait(
        FunctionName=FUNCTION_NAME
    )
    return str(updated["FunctionArn"])


def _unqualified_arn(function_arn: str) -> str:
    """Strip a trailing version or alias qualifier from a function ARN.

    The integration must target the unqualified function so the resource policy
    granted to API Gateway keeps applying after each code publish.
    """
    parts = function_arn.split(":")
    return ":".join(parts[:7]) if len(parts) == 8 else function_arn


def ensure_http_api(
    apigw: Any, lambda_client: Any, region: str, function_arn: str
) -> str:
    """Create or reuse an HTTP API fronting the Sage API function.

    A public Lambda Function URL is blocked by organization policy in some
    accounts (anonymous ``lambda:InvokeFunctionUrl`` is denied), so the API is
    fronted by API Gateway instead. HTTP API payload format 2.0 has the same
    shape as the Function URL payload, so the WSGI adapter is unchanged.
    """
    target = _unqualified_arn(function_arn)
    existing = [
        api
        for api in apigw.get_apis(MaxResults="500").get("Items", [])
        if api.get("Name") == HTTP_API_NAME
    ]
    if len(existing) > 1:
        raise ValueError(f"multiple HTTP APIs are named {HTTP_API_NAME}")

    if existing:
        api = existing[0]
    else:
        # Quick-create builds the proxy integration, $default route, and an
        # auto-deploying $default stage in one call.
        api = apigw.create_api(
            Name=HTTP_API_NAME,
            ProtocolType="HTTP",
            Target=target,
            Description="Shared Sage API tenant data boundary",
        )

    api_id = str(api["ApiId"])
    account_id = target.split(":")[4]

    # Quick-create may record whatever ARN it was handed, including a version
    # qualifier, which the unqualified permission does not cover.
    for integration in apigw.get_integrations(ApiId=api_id).get("Items", []):
        if integration.get("IntegrationUri") != target:
            apigw.update_integration(
                ApiId=api_id,
                IntegrationId=integration["IntegrationId"],
                IntegrationUri=target,
                PayloadFormatVersion="2.0",
            )

    try:
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="HttpApiInvoke",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{region}:{account_id}:{api_id}/*/*",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceConflictException":
            raise

    endpoint = api.get("ApiEndpoint") or apigw.get_api(ApiId=api_id)["ApiEndpoint"]
    return str(endpoint).rstrip("/")


def remove_blocked_function_url(lambda_client: Any) -> bool:
    """Delete a previously created Function URL that organization policy blocks."""
    try:
        lambda_client.get_function_url_config(FunctionName=FUNCTION_NAME)
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        return False
    lambda_client.delete_function_url_config(FunctionName=FUNCTION_NAME)
    try:
        lambda_client.remove_permission(
            FunctionName=FUNCTION_NAME, StatementId="FunctionUrlPublicInvoke"
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    return True


def main() -> None:
    """Render the plan locally, or deploy after explicit public-endpoint consent."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--lane-a-pool-id", required=True)
    parser.add_argument("--lane-a-client-id", required=True)
    parser.add_argument("--lane-b-pool-id", required=True)
    parser.add_argument("--lane-b-client-id", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument(
        "--allow-public-url",
        action="store_true",
        help="Acknowledge that the HTTP API endpoint is internet reachable.",
    )
    args = parser.parse_args()

    lanes = {
        TENANT_A: {
            "poolId": args.lane_a_pool_id,
            "clientId": args.lane_a_client_id,
        },
        TENANT_B: {
            "poolId": args.lane_b_pool_id,
            "clientId": args.lane_b_client_id,
        },
    }
    environment = build_configuration(args.region, lanes)

    if args.render:
        issuers = json.loads(environment["SAGE_API_ISSUER_MAP"])
        keys = json.loads(environment["SAGE_API_PUBLIC_KEYS"])
        print(
            json.dumps(
                {
                    "functionName": FUNCTION_NAME,
                    "region": args.region,
                    "runtime": RUNTIME,
                    "architecture": ARCHITECTURE,
                    "handler": HANDLER,
                    "reservedConcurrency": RESERVED_CONCURRENCY,
                    "functionUrlAuthType": "NONE",
                    "sourceControl": "deployment_asserted_record_as_unavailable",
                    "issuers": [
                        {
                            "issuer": entry["issuer"],
                            "expectedTenantId": entry["expected_tenant_id"],
                            "trustedClientIds": entry["trusted_client_ids"],
                            "publishedKeyCount": len(
                                keys[entry["issuer"]]["keys"]
                            ),
                        }
                        for entry in issuers
                    ],
                    "awsMutationCallsIssued": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if not args.allow_public_url:
        raise SystemExit(
            "Refusing to deploy without --allow-public-url. This deployment "
            "removes any Lambda Function URL and fronts the function with an "
            "API Gateway HTTP API that has no gateway-level authorizer, so the "
            "endpoint is internet-reachable and every request is authorized "
            "only by the Sage API's own independent JWT validation and its "
            "deployment-asserted source path."
        )

    iam = boto3.client("iam")
    lambda_client = boto3.client("lambda", region_name=args.region)
    apigw = boto3.client("apigatewayv2", region_name=args.region)

    role_arn = ensure_role(iam)
    package = build_zip(("sage_api", "sage_identity"), ("pyjwt[crypto]==2.13.0",))
    function_arn = deploy_function(lambda_client, role_arn, package, environment)
    lambda_client.put_function_concurrency(
        FunctionName=FUNCTION_NAME,
        ReservedConcurrentExecutions=RESERVED_CONCURRENCY,
    )
    removed_url = remove_blocked_function_url(lambda_client)
    sage_api_url = ensure_http_api(apigw, lambda_client, args.region, function_arn)

    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "region": args.region,
                "functionName": FUNCTION_NAME,
                "functionArn": function_arn,
                "httpApiName": HTTP_API_NAME,
                "sageApiUrl": sage_api_url,
                "reservedConcurrency": RESERVED_CONCURRENCY,
                "ingress": "http_api_no_authorizer",
                "removedBlockedFunctionUrl": removed_url,
                "approvedSourcePath": SOURCE_PATH,
                "sourceSignalClassification": "unavailable",
                "issuers": [
                    entry["issuer"]
                    for entry in json.loads(environment["SAGE_API_ISSUER_MAP"])
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Deployed {FUNCTION_NAME}; wrote {OUTPUT_FILE}")
    print(f"SAGE_API_URL={sage_api_url}")


if __name__ == "__main__":
    main()
