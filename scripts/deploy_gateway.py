#!/usr/bin/env python3
"""Deploy the AgentCore Gateway with Cognito OAuth M2M authentication.

Steps:
  1. Resolve MCP server runtime ARN from .bedrock_agentcore.yaml
  2. Create (or reuse) a Cognito User Pool, domain, resource server, and M2M client
  3. Create an AgentCore OAuth2 credential provider (token vault)
  4. Create the AgentCore Gateway with semantic search enabled
  5. Add the MCP server as a gateway target with OAuth credentials
  6. Synchronize gateway targets
  7. Save all outputs to scripts/gateway_output.json

Prerequisites:
  - AWS credentials configured (aws configure)
  - bedrock-agentcore-starter-toolkit installed (uv add bedrock-agentcore)
  - MCP server deployed (deploy_mcp.sh) — runtime ARN needed

Usage:
  uv run python scripts/deploy_gateway.py

Environment variables (optional overrides):
  AWS_REGION          — defaults to us-east-1
  MCP_RUNTIME_ARN     — MCP server runtime ARN (auto-detected from .bedrock_agentcore.yaml)
  GATEWAY_NAME        — gateway name prefix (defaults to sage-gateway)
  COGNITO_POOL_NAME   — Cognito User Pool name (defaults to sage-mcp-pool)
"""

import json
import os
import socket
import sys
import time
import urllib.parse
from pathlib import Path

# Force IPv4 — macOS often resolves AWS endpoints to IPv6 but the route hangs.
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(*args, **kwargs):
    results = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else results

socket.getaddrinfo = _ipv4_getaddrinfo

import boto3
import yaml

# ── Configuration ─────────────────────────────────────────────────────

REGION = os.environ.get("AWS_REGION", "us-east-1")
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_FILE = SCRIPT_DIR / "gateway_output.json"

GATEWAY_NAME = os.environ.get("GATEWAY_NAME", "sage-gateway")
COGNITO_POOL_NAME = os.environ.get("COGNITO_POOL_NAME", "sage-mcp-pool")
RESOURCE_SERVER_ID = "sage-mcp"
SCOPE_NAME = "tools"
FULL_SCOPE = f"{RESOURCE_SERVER_ID}/{SCOPE_NAME}"
M2M_CLIENT_NAME = "sage-gateway-m2m"
CREDENTIAL_PROVIDER_NAME = "sage-mcp-oauth"
TARGET_NAME = "sage-mcp-target"


def load_previous_output() -> dict:
    """Load previously saved gateway output if it exists."""
    if OUTPUT_FILE.exists():
        try:
            return json.loads(OUTPUT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def step0_resolve_mcp_arn() -> tuple[str, str]:
    """Resolve MCP server runtime ARN and build endpoint URI."""
    print("Step 0: Resolving MCP server runtime ARN...")

    mcp_arn = os.environ.get("MCP_RUNTIME_ARN", "")
    if not mcp_arn:
        config_path = PROJECT_ROOT / ".bedrock_agentcore.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        agent = cfg.get("agents", {}).get("sage_mcp_server", {})
        mcp_arn = agent.get("bedrock_agentcore", {}).get("agent_arn", "")
        if not mcp_arn:
            print("ERROR: MCP runtime ARN not found in .bedrock_agentcore.yaml", file=sys.stderr)
            sys.exit(1)

    encoded_arn = urllib.parse.quote(mcp_arn, safe="")
    endpoint_uri = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations"

    print(f"  MCP Runtime ARN: {mcp_arn}")
    print(f"  MCP Endpoint URI: {endpoint_uri}")
    return mcp_arn, endpoint_uri


def step1_cognito_pool(cognito: object, prev: dict) -> str:
    """Create or reuse a Cognito User Pool."""
    print("\nStep 1: Setting up Cognito User Pool...")

    saved_id = prev.get("cognitoPoolId")
    if saved_id:
        print(f"  Reusing pool from gateway_output.json: {saved_id}")
        return saved_id

    resp = cognito.list_user_pools(MaxResults=60)
    for pool in resp.get("UserPools", []):
        if pool["Name"] == COGNITO_POOL_NAME:
            print(f"  Found existing pool: {pool['Id']}")
            return pool["Id"]

    resp = cognito.create_user_pool(PoolName=COGNITO_POOL_NAME)
    pool_id = resp["UserPool"]["Id"]
    print(f"  Created pool: {pool_id}")
    return pool_id


def step2_cognito_domain(cognito: object, pool_id: str) -> str:
    """Create Cognito domain (required for token endpoint)."""
    domain_prefix = f"sage-mcp-{pool_id.split('_')[-1]}".lower()
    print(f"\nStep 2: Setting up Cognito domain: {domain_prefix}")

    try:
        cognito.create_user_pool_domain(Domain=domain_prefix, UserPoolId=pool_id)
        print("  Created domain.")
    except cognito.exceptions.InvalidParameterException:
        print("  Domain already exists, continuing...")
    except Exception as e:
        print(f"  Domain setup note: {e}")

    return domain_prefix


def step3_resource_server(cognito: object, pool_id: str) -> None:
    """Create or update the Cognito resource server with custom scope."""
    print("\nStep 3: Creating Cognito resource server...")

    scopes = [{"ScopeName": SCOPE_NAME, "ScopeDescription": "Access to Sage MCP tools"}]

    try:
        cognito.describe_resource_server(UserPoolId=pool_id, Identifier=RESOURCE_SERVER_ID)
        print("  Resource server exists, updating...")
        cognito.update_resource_server(
            UserPoolId=pool_id, Identifier=RESOURCE_SERVER_ID,
            Name="Sage MCP Server", Scopes=scopes,
        )
    except cognito.exceptions.ResourceNotFoundException:
        print("  Creating resource server...")
        cognito.create_resource_server(
            UserPoolId=pool_id, Identifier=RESOURCE_SERVER_ID,
            Name="Sage MCP Server", Scopes=scopes,
        )

    print(f"  Resource server: {RESOURCE_SERVER_ID} (scope: {FULL_SCOPE})")


def step4_m2m_client(cognito: object, pool_id: str) -> tuple[str, str]:
    """Create or reuse the M2M app client with client_credentials grant."""
    print("\nStep 4: Creating Cognito M2M app client...")

    resp = cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)
    for c in resp.get("UserPoolClients", []):
        if c["ClientName"] == M2M_CLIENT_NAME:
            client_id = c["ClientId"]
            print(f"  Reusing existing M2M client: {client_id}")
            desc = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client_id)
            secret = desc["UserPoolClient"].get("ClientSecret", "")
            return client_id, secret

    print(f"  Creating new M2M app client: {M2M_CLIENT_NAME}")
    resp = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=M2M_CLIENT_NAME,
        GenerateSecret=True,
        AllowedOAuthFlows=["client_credentials"],
        AllowedOAuthScopes=[FULL_SCOPE],
        AllowedOAuthFlowsUserPoolClient=True,
    )
    client_id = resp["UserPoolClient"]["ClientId"]
    secret = resp["UserPoolClient"].get("ClientSecret", "")
    print(f"  Created M2M client: {client_id}")
    return client_id, secret


def step5_credential_provider(
    pool_id: str, discovery_url: str, client_id: str, client_secret: str,
) -> str:
    """Create AgentCore OAuth2 credential provider via boto3."""
    print("\nStep 5: Creating AgentCore OAuth2 credential provider...")

    ac = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # Check if it already exists
    try:
        resp = ac.list_oauth2_credential_providers()
        for p in resp.get("credentialProviders", []):
            if p.get("name") == CREDENTIAL_PROVIDER_NAME:
                arn = p["credentialProviderArn"]
                print(f"  Reusing existing credential provider: {arn}")
                return arn
    except Exception as e:
        print(f"  Note: Could not list credential providers: {e}")

    # Create new credential provider using CustomOauth2 with Cognito discovery URL
    print(f"  Creating credential provider: {CREDENTIAL_PROVIDER_NAME}")
    resp = ac.create_oauth2_credential_provider(
        name=CREDENTIAL_PROVIDER_NAME,
        credentialProviderVendor="CustomOauth2",
        oauth2ProviderConfigInput={
            "customOauth2ProviderConfig": {
                "oauthDiscovery": {
                    "discoveryUrl": discovery_url,
                },
                "clientId": client_id,
                "clientSecret": client_secret,
            }
        },
    )
    arn = resp["credentialProviderArn"]
    print(f"  Credential Provider ARN: {arn}")
    return arn


def step6_gateway(prev: dict) -> tuple[str, str, str, str]:
    """Create or reuse the AgentCore Gateway with semantic search."""
    print("\nStep 6: Creating AgentCore Gateway...")

    ac = boto3.client("bedrock-agentcore-control", region_name=REGION)

    if prev.get("gatewayArn"):
        print(f"  Reusing existing gateway from gateway_output.json")
        arn = prev["gatewayArn"]
        gw_id = prev["gatewayId"]
        url = prev["gatewayUrl"]
        role = prev.get("roleArn", "")
        print(f"  Gateway ARN: {arn}")
        print(f"  Gateway URL: {url}")
        return arn, gw_id, url, role

    # Resolve the gateway execution role
    iam = boto3.client("iam")
    try:
        role_arn = iam.get_role(RoleName="AgentCoreGatewayExecutionRole")["Role"]["Arn"]
    except Exception as e:
        print(f"ERROR: Could not find AgentCoreGatewayExecutionRole: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if gateway already exists
    resp = ac.list_gateways()
    for gw in resp.get("gateways", []):
        if gw.get("name") == GATEWAY_NAME:
            arn = gw["gatewayArn"]
            gw_id = arn.rsplit("/", 1)[-1]
            url = gw.get("gatewayUrl", f"https://{gw_id}.gateway.bedrock-agentcore.{REGION}.amazonaws.com/mcp")
            print(f"  Found existing gateway: {arn}")
            return arn, gw_id, url, role_arn

    print(f"  Creating new gateway: {GATEWAY_NAME}")
    resp = ac.create_gateway(
        name=GATEWAY_NAME,
        roleArn=role_arn,
        protocolType="MCP",
        protocolConfiguration={
            "mcp": {
                "searchType": "SEMANTIC",
            }
        },
        authorizerType="NONE",
    )
    arn = resp["gatewayArn"]
    gw_id = arn.rsplit("/", 1)[-1]
    url = resp.get("gatewayUrl", f"https://{gw_id}.gateway.bedrock-agentcore.{REGION}.amazonaws.com/mcp")

    print(f"  Gateway ARN: {arn}")
    print(f"  Gateway ID: {gw_id}")
    print(f"  Gateway URL: {url}")
    return arn, gw_id, url, role_arn


def step7_gateway_target(
    gateway_id: str, mcp_endpoint_uri: str, credential_provider_arn: str,
) -> str:
    """Add MCP server as gateway target with OAuth M2M credentials."""
    print("\nStep 7: Adding MCP server target with OAuth M2M credentials...")

    ac = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # List existing targets — response key is "items"
    deleted_any = False
    try:
        existing = ac.list_gateway_targets(gatewayIdentifier=gateway_id)
        for t in existing.get("items", []):
            tid = t["targetId"]
            status = t.get("status", "")
            print(f"  Found existing target '{t['name']}' (ID: {tid}, status: {status}), deleting...")
            ac.delete_gateway_target(gatewayIdentifier=gateway_id, targetId=tid)
            print(f"  Deleted {tid}.")
            deleted_any = True
    except Exception as e:
        print(f"  Note: Could not clean up existing targets: {e}")

    # Wait for deletions to propagate before creating
    if deleted_any:
        print("  Waiting for target deletions to propagate...", end="", flush=True)
        for _ in range(30):
            time.sleep(3)
            print(".", end="", flush=True)
            try:
                remaining = ac.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", [])
                if not remaining:
                    break
            except Exception:
                break
        print(" done.")

    # Create target with correct AgentCore OAuth2 credential provider ARN
    resp = ac.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name=TARGET_NAME,
        description="FastMCP server hosting Sage context tools and data tools",
        targetConfiguration={
            "mcp": {"mcpServer": {"endpoint": mcp_endpoint_uri}},
        },
        credentialProviderConfigurations=[
            {
                "credentialProviderType": "OAUTH",
                "credentialProvider": {
                    "oauthCredentialProvider": {
                        "providerArn": credential_provider_arn,
                        "grantType": "CLIENT_CREDENTIALS",
                        "scopes": [FULL_SCOPE],
                    }
                },
            }
        ],
        metadataConfiguration={
            "allowedRequestHeaders": [
                "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id",
            ]
        },
    )
    target_id = resp.get("targetId", "unknown")
    print(f"  Created MCP target: {target_id}")
    print(f"  Target status: {resp.get('status', 'unknown')}")

    # Synchronize
    print("  Synchronizing gateway targets...")
    try:
        ac.synchronize_gateway_targets(gatewayIdentifier=gateway_id, targetIdList=[target_id])
        print("  Target synchronization initiated.")
    except Exception as e:
        print(f"  Warning: Target sync failed (may complete async): {e}")

    return target_id


def step8_save_outputs(
    gateway_arn: str, gateway_id: str, gateway_url: str, role_arn: str,
    mcp_arn: str, mcp_endpoint_uri: str, pool_id: str,
    m2m_client_id: str, m2m_client_secret: str, credential_provider_arn: str,
) -> None:
    """Save all deployment outputs to gateway_output.json."""
    print("\nStep 8: Saving deployment outputs...")

    domain_prefix = f"sage-mcp-{pool_id.split('_')[-1]}".lower()
    token_endpoint = f"https://{domain_prefix}.auth.{REGION}.amazoncognito.com/oauth2/token"

    output = {
        "gatewayArn": gateway_arn,
        "gatewayId": gateway_id,
        "gatewayUrl": gateway_url,
        "roleArn": role_arn,
        "mcpServerArn": mcp_arn,
        "mcpEndpointUri": mcp_endpoint_uri,
        "cognitoPoolId": pool_id,
        "cognitoResourceServerId": RESOURCE_SERVER_ID,
        "cognitoM2mClientId": m2m_client_id,
        "cognitoM2mClientSecret": m2m_client_secret,
        "cognitoTokenEndpoint": token_endpoint,
        "cognitoScope": FULL_SCOPE,
        "credentialProviderArn": credential_provider_arn,
        "region": REGION,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2) + "\n")
    print(f"  Saved to: {OUTPUT_FILE}")


def main() -> None:
    """Run all deployment steps."""
    print("=== Deploying Sage AgentCore Gateway ===")
    print(f"Region: {REGION}\n")

    prev = load_previous_output()
    cognito = boto3.client("cognito-idp", region_name=REGION)

    # Step 0: Resolve MCP ARN
    mcp_arn, mcp_endpoint_uri = step0_resolve_mcp_arn()

    # Step 1: Cognito User Pool
    pool_id = step1_cognito_pool(cognito, prev)
    discovery_url = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
    print(f"  Discovery URL: {discovery_url}")

    # Step 2: Cognito domain
    step2_cognito_domain(cognito, pool_id)

    # Step 3: Resource server
    step3_resource_server(cognito, pool_id)

    # Step 4: M2M client
    m2m_client_id, m2m_client_secret = step4_m2m_client(cognito, pool_id)

    # Step 5: Credential provider
    credential_provider_arn = step5_credential_provider(
        pool_id, discovery_url, m2m_client_id, m2m_client_secret,
    )

    # Step 6: Gateway
    gateway_arn, gateway_id, gateway_url, role_arn = step6_gateway(prev)

    # Step 7: Gateway target
    step7_gateway_target(gateway_id, mcp_endpoint_uri, credential_provider_arn)

    # Step 8: Save outputs
    step8_save_outputs(
        gateway_arn, gateway_id, gateway_url, role_arn,
        mcp_arn, mcp_endpoint_uri, pool_id,
        m2m_client_id, m2m_client_secret, credential_provider_arn,
    )

    print("\n=== Gateway deployment complete ===\n")
    print(f"  Gateway:             {gateway_id}")
    print(f"  Gateway URL:         {gateway_url}")
    print(f"  MCP Server Target:   {TARGET_NAME} (OAuth M2M)")
    print(f"  Cognito Pool:        {pool_id}")
    print(f"  Credential Provider: {credential_provider_arn}")
    print(f"\nNext steps:")
    print(f"  1. Redeploy MCP server with JWT inbound auth:")
    print(f"     bash scripts/deploy_mcp.sh")
    print(f"  2. Deploy the agent:")
    print(f"     bash scripts/deploy_agent.sh")
    print(f"  3. Get a bearer token for the frontend:")
    print(f"     uv run agentcore identity get-cognito-inbound-token --region {REGION}")


if __name__ == "__main__":
    main()
