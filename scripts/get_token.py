#!/usr/bin/env python3
"""Get an M2M access token from Cognito for the frontend (Phase 1 only).

This script is for Phase 1 deployments that use static M2M tokens.
In Phase 2, the frontend authenticates users directly via Cognito and
obtains ID tokens — this script is not needed.

Bypasses macOS DNS cache issues by resolving via nslookup and connecting
directly to the IP with SNI.

Usage:
  python3 scripts/get_token.py

Prerequisites:
  - Phase 1 deployment: deploy_gateway.sh must have been run first
  - gateway_output.json must exist with Cognito M2M credentials
"""

import json
import socket
import ssl
import sys
from pathlib import Path

# Force IPv4
_orig = socket.getaddrinfo
def _ipv4(*a, **k):
    r = _orig(*a, **k)
    v4 = [x for x in r if x[0] == socket.AF_INET]
    return v4 if v4 else r
socket.getaddrinfo = _ipv4

import base64
import boto3
import http.client

try:
    with open("scripts/gateway_output.json") as f:
        gw = json.load(f)
except FileNotFoundError:
    print("ERROR: scripts/gateway_output.json not found", file=sys.stderr)
    print("This script is for Phase 1 deployments only.", file=sys.stderr)
    print("Run: bash scripts/deploy_gateway.sh", file=sys.stderr)
    sys.exit(1)

pool_id = gw["cognitoPoolId"]
client_id = gw["cognitoM2mClientId"]
region = gw["region"]

cognito = boto3.client("cognito-idp", region_name=region)
desc = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client_id)
client_secret = desc["UserPoolClient"].get("ClientSecret", "")

domain_prefix = f"sage-mcp-{pool_id.split('_')[-1]}".lower()
host = f"{domain_prefix}.auth.{region}.amazoncognito.com"

# Resolve IP manually to bypass stale DNS cache
import subprocess
result = subprocess.run(["nslookup", host], capture_output=True, text=True, timeout=5)
ip = None
for line in result.stdout.splitlines():
    line = line.strip()
    if line.startswith("Address:") and not line.endswith("#53"):
        ip = line.split()[-1]
        # Skip IPv6
        if ":" not in ip:
            break
        ip = None

if not ip:
    print(f"Could not resolve {host}", file=sys.stderr)
    print("Try: sudo dscacheutil -flushcache && python3 scripts/get_token.py", file=sys.stderr)
    sys.exit(1)

print(f"Resolved {host} -> {ip}", file=sys.stderr)

# Connect directly to IP with SNI for proper TLS
ctx = ssl.create_default_context()
raw_sock = socket.create_connection((ip, 443), timeout=10)
ssl_sock = ctx.wrap_socket(raw_sock, server_hostname=host)
conn = http.client.HTTPSConnection(host, 443, context=ctx, timeout=10)
conn.sock = ssl_sock

creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
body = "grant_type=client_credentials&scope=sage-mcp/tools"

conn.request("POST", "/oauth2/token", body=body, headers={
    "Host": host,
    "Content-Type": "application/x-www-form-urlencoded",
    "Authorization": f"Basic {creds}",
})

resp = conn.getresponse()
data = resp.read().decode()

if resp.status != 200:
    print(f"Error {resp.status}: {data}", file=sys.stderr)
    sys.exit(1)

token_data = json.loads(data)
access_token = token_data["access_token"]
expires_in = token_data.get("expires_in", "?")
print(f"Expires in: {expires_in} seconds", file=sys.stderr)
print(access_token)

# Auto-update frontend/.env.local
env_file = Path(__file__).resolve().parent.parent / "frontend" / ".env.local"
if env_file.exists():
    content = env_file.read_text()
    import re
    new_content = re.sub(
        r"^VITE_AGENT_BEARER_TOKEN=.*$",
        f"VITE_AGENT_BEARER_TOKEN={access_token}",
        content,
        flags=re.MULTILINE,
    )
    if new_content != content:
        env_file.write_text(new_content)
        print(f"Updated {env_file}", file=sys.stderr)
    else:
        print(f"No VITE_AGENT_BEARER_TOKEN line found in {env_file}", file=sys.stderr)
else:
    print(f"{env_file} not found — token printed to stdout only", file=sys.stderr)
