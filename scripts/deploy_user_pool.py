#!/usr/bin/env python3
"""Create the Phase 2 Cognito User Pool for tenant JWT authentication.

Creates a Cognito User Pool named ``sage-tenant-pool`` with a custom
attribute ``custom:tenant_id``, then creates two app clients:

  - ``sage-axa-client``     — pre-seeded with tenant_id = "axa"
  - ``sage-allianz-client`` — pre-seeded with tenant_id = "allianz"

Both clients use the USER_PASSWORD_AUTH flow so the React frontend can
authenticate directly via the Cognito Identity SDK without a hosted UI.
The ``custom:tenant_id`` attribute is included in the ID token claims via
a pre-token-generation Lambda trigger (or read-only attribute mapping).

Outputs are saved to ``scripts/user_pool_output.json`` for use by
``deploy_agent.sh`` (JWT inbound auth) and the React frontend.

Usage:
  uv run python scripts/deploy_user_pool.py

Prerequisites:
  - AWS credentials configured (aws configure)
  - uv environment activated (source .venv/bin/activate)
"""

import json
import os
import socket
import sys
import time
from pathlib import Path

# Force IPv4 — macOS often resolves AWS endpoints to IPv6 but the route hangs.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(*args, **kwargs):
    """Prefer IPv4 addresses to avoid macOS IPv6 routing issues."""
    results = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else results


socket.getaddrinfo = _ipv4_getaddrinfo

import boto3

# ── Configuration ─────────────────────────────────────────────────────

REGION = os.environ.get("AWS_REGION", "us-east-1")
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "user_pool_output.json"

POOL_NAME = "sage-tenant-pool"
AXA_CLIENT_NAME = "sage-axa-client"
ALLIANZ_CLIENT_NAME = "sage-allianz-client"
DOMAIN_PREFIX_BASE = "sage-tenant"


def load_previous_output() -> dict:
    """Load previously saved user pool output if it exists.

    Returns:
        Previously saved output dict, or empty dict if not found.
    """
    if OUTPUT_FILE.exists():
        try:
            return json.loads(OUTPUT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def step1_user_pool(cognito: object, prev: dict) -> str:
    """Create or reuse the ``sage-tenant-pool`` Cognito User Pool.

    The pool includes a custom attribute ``custom:tenant_id`` that is
    mutable and included in ID token claims.

    Args:
        cognito: Boto3 Cognito IDP client.
        prev: Previously saved output dict.

    Returns:
        User Pool ID string.
    """
    print("\nStep 1: Setting up Cognito User Pool...")

    saved_id = prev.get("userPoolId")
    if saved_id:
        print(f"  Reusing pool from user_pool_output.json: {saved_id}")
        return saved_id

    # Check if pool already exists
    resp = cognito.list_user_pools(MaxResults=60)
    for pool in resp.get("UserPools", []):
        if pool["Name"] == POOL_NAME:
            print(f"  Found existing pool: {pool['Id']}")
            return pool["Id"]

    print(f"  Creating new User Pool: {POOL_NAME}")
    resp = cognito.create_user_pool(
        PoolName=POOL_NAME,
        Schema=[
            {
                "Name": "tenant_id",
                "AttributeDataType": "String",
                "Mutable": True,
                "Required": False,
                "StringAttributeConstraints": {
                    "MinLength": "1",
                    "MaxLength": "64",
                },
            }
        ],
        # Allow users to sign in with username
        UsernameAttributes=[],
        # Auto-verify email (not required for M2M / client_credentials)
        AutoVerifiedAttributes=[],
        # Password policy — relaxed for demo
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 8,
                "RequireUppercase": False,
                "RequireLowercase": False,
                "RequireNumbers": False,
                "RequireSymbols": False,
            }
        },
    )
    pool_id = resp["UserPool"]["Id"]
    print(f"  Created User Pool: {pool_id}")
    return pool_id


def step2_cognito_domain(cognito: object, pool_id: str, prev: dict) -> str:
    """Create a Cognito hosted UI domain for the tenant pool.

    Args:
        cognito: Boto3 Cognito IDP client.
        pool_id: User Pool ID.
        prev: Previously saved output dict.

    Returns:
        Domain prefix string.
    """
    saved_domain = prev.get("cognitoDomain")
    if saved_domain:
        print(f"\nStep 2: Reusing Cognito domain: {saved_domain}")
        return saved_domain

    domain_prefix = f"{DOMAIN_PREFIX_BASE}-{pool_id.split('_')[-1]}".lower()
    print(f"\nStep 2: Setting up Cognito domain: {domain_prefix}")

    try:
        cognito.create_user_pool_domain(Domain=domain_prefix, UserPoolId=pool_id)
        print("  Created domain.")
    except cognito.exceptions.InvalidParameterException:
        print("  Domain already exists, continuing...")
    except Exception as e:
        print(f"  Domain setup note: {e}")

    return domain_prefix


def step3_app_client(
    cognito: object,
    pool_id: str,
    client_name: str,
    tenant_id_value: str,
    prev_client_id: str | None,
) -> tuple[str, str]:
    """Create or reuse a Cognito app client for a specific tenant.

    The client uses USER_PASSWORD_AUTH so the React frontend can
    authenticate directly. The ``custom:tenant_id`` attribute is set
    on users created for this client.

    Args:
        cognito: Boto3 Cognito IDP client.
        pool_id: User Pool ID.
        client_name: App client name (e.g. "sage-axa-client").
        tenant_id_value: Tenant ID value (e.g. "axa").
        prev_client_id: Previously saved client ID, or None.

    Returns:
        Tuple of (client_id, client_secret).
    """
    print(f"\nStep 3/{client_name}: Setting up app client '{client_name}'...")

    if prev_client_id:
        print(f"  Reusing existing client: {prev_client_id}")
        try:
            desc = cognito.describe_user_pool_client(
                UserPoolId=pool_id, ClientId=prev_client_id
            )
            secret = desc["UserPoolClient"].get("ClientSecret", "")
            return prev_client_id, secret
        except Exception:
            print("  Could not describe saved client — will recreate.")

    # Check if client already exists
    resp = cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)
    for c in resp.get("UserPoolClients", []):
        if c["ClientName"] == client_name:
            client_id = c["ClientId"]
            print(f"  Found existing client: {client_id}")
            desc = cognito.describe_user_pool_client(
                UserPoolId=pool_id, ClientId=client_id
            )
            secret = desc["UserPoolClient"].get("ClientSecret", "")
            return client_id, secret

    print(f"  Creating app client: {client_name} (tenant_id={tenant_id_value})")
    resp = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=client_name,
        GenerateSecret=False,  # Public client — no secret needed for SPA
        ExplicitAuthFlows=[
            "ALLOW_USER_SRP_AUTH",
            "ALLOW_USER_PASSWORD_AUTH",
            "ALLOW_REFRESH_TOKEN_AUTH",
        ],
        # Read/write access to custom:tenant_id
        ReadAttributes=["custom:tenant_id", "email"],
        WriteAttributes=["custom:tenant_id", "email"],
        # Token validity
        AccessTokenValidity=1,
        IdTokenValidity=1,
        RefreshTokenValidity=30,
        TokenValidityUnits={
            "AccessToken": "hours",
            "IdToken": "hours",
            "RefreshToken": "days",
        },
    )
    client_id = resp["UserPoolClient"]["ClientId"]
    secret = resp["UserPoolClient"].get("ClientSecret", "")
    print(f"  Created app client: {client_id}")
    return client_id, secret


def step4_demo_users(
    cognito: object,
    pool_id: str,
    axa_client_id: str,
    allianz_client_id: str,
) -> None:
    """Create demo users for AXA and Allianz tenants.

    Creates:
      - axa-user / AXApassword1  (custom:tenant_id = "axa")
      - allianz-user / Allianzpassword1  (custom:tenant_id = "allianz")

    Args:
        cognito: Boto3 Cognito IDP client.
        pool_id: User Pool ID.
        axa_client_id: AXA app client ID (unused — users are pool-level).
        allianz_client_id: Allianz app client ID (unused).
    """
    print("\nStep 4: Creating demo users...")

    demo_users = [
        {
            "username": "axa-user",
            "password": "AXApassword1",
            "tenant_id": "axa",
        },
        {
            "username": "allianz-user",
            "password": "Allianzpassword1",
            "tenant_id": "allianz",
        },
    ]

    for user in demo_users:
        username = user["username"]
        password = user["password"]
        tenant_id = user["tenant_id"]

        try:
            cognito.admin_create_user(
                UserPoolId=pool_id,
                Username=username,
                TemporaryPassword=password,
                UserAttributes=[
                    {"Name": "custom:tenant_id", "Value": tenant_id},
                ],
                MessageAction="SUPPRESS",  # Don't send welcome email
            )
            print(f"  Created user: {username} (tenant_id={tenant_id})")

            # Set permanent password (skip FORCE_CHANGE_PASSWORD state)
            cognito.admin_set_user_password(
                UserPoolId=pool_id,
                Username=username,
                Password=password,
                Permanent=True,
            )
            print(f"  Set permanent password for: {username}")

        except cognito.exceptions.UsernameExistsException:
            print(f"  User already exists: {username}")
            # Update tenant_id attribute in case it changed
            try:
                cognito.admin_update_user_attributes(
                    UserPoolId=pool_id,
                    Username=username,
                    UserAttributes=[
                        {"Name": "custom:tenant_id", "Value": tenant_id},
                    ],
                )
                print(f"  Updated tenant_id for: {username}")
            except Exception as e:
                print(f"  Warning: Could not update {username}: {e}")


def step5_save_outputs(
    pool_id: str,
    domain_prefix: str,
    axa_client_id: str,
    allianz_client_id: str,
) -> None:
    """Save all deployment outputs to user_pool_output.json.

    Args:
        pool_id: Cognito User Pool ID.
        domain_prefix: Cognito hosted UI domain prefix.
        axa_client_id: AXA app client ID.
        allianz_client_id: Allianz app client ID.
    """
    print("\nStep 5: Saving deployment outputs...")

    discovery_url = (
        f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}"
        "/.well-known/openid-configuration"
    )
    cognito_domain = f"{domain_prefix}.auth.{REGION}.amazoncognito.com"

    output = {
        "userPoolId": pool_id,
        "cognitoDomain": domain_prefix,
        "cognitoHostedUiDomain": cognito_domain,
        "discoveryUrl": discovery_url,
        "axaClientId": axa_client_id,
        "allianzClientId": allianz_client_id,
        "region": REGION,
        "demoUsers": {
            "axa": {"username": "axa-user", "password": "AXApassword1"},
            "allianz": {"username": "allianz-user", "password": "Allianzpassword1"},
        },
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2) + "\n")
    print(f"  Saved to: {OUTPUT_FILE}")


def main() -> None:
    """Run all deployment steps for the Phase 2 Cognito User Pool."""
    print("=== Deploying Sage Phase 2 Cognito User Pool ===")
    print(f"Region: {REGION}\n")

    prev = load_previous_output()
    cognito = boto3.client("cognito-idp", region_name=REGION)

    # Step 1: User Pool
    pool_id = step1_user_pool(cognito, prev)

    # Step 2: Cognito domain
    domain_prefix = step2_cognito_domain(cognito, pool_id, prev)

    # Step 3a: AXA app client
    axa_client_id, _ = step3_app_client(
        cognito,
        pool_id,
        AXA_CLIENT_NAME,
        "axa",
        prev.get("axaClientId"),
    )

    # Step 3b: Allianz app client
    allianz_client_id, _ = step3_app_client(
        cognito,
        pool_id,
        ALLIANZ_CLIENT_NAME,
        "allianz",
        prev.get("allianzClientId"),
    )

    # Step 4: Demo users
    step4_demo_users(cognito, pool_id, axa_client_id, allianz_client_id)

    # Step 5: Save outputs
    step5_save_outputs(pool_id, domain_prefix, axa_client_id, allianz_client_id)

    discovery_url = (
        f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}"
        "/.well-known/openid-configuration"
    )

    print("\n=== User Pool deployment complete ===\n")
    print(f"  User Pool ID:      {pool_id}")
    print(f"  AXA Client ID:     {axa_client_id}")
    print(f"  Allianz Client ID: {allianz_client_id}")
    print(f"  Discovery URL:     {discovery_url}")
    print(f"\nNext steps:")
    print(f"  1. Update deploy_agent.sh to use this pool for JWT inbound auth:")
    print(f"     bash scripts/deploy_agent.sh")
    print(f"  2. Update frontend/.env.local with Cognito client IDs:")
    print(f"     VITE_COGNITO_USER_POOL_ID={pool_id}")
    print(f"     VITE_COGNITO_AXA_CLIENT_ID={axa_client_id}")
    print(f"     VITE_COGNITO_ALLIANZ_CLIENT_ID={allianz_client_id}")
    print(f"     VITE_COGNITO_DOMAIN={domain_prefix}.auth.{REGION}.amazoncognito.com")


if __name__ == "__main__":
    main()
