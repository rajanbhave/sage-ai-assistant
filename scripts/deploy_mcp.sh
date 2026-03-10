#!/usr/bin/env bash
# Deploy the Sage MCP server to AgentCore Runtime with JWT inbound authorization.
#
# Prerequisites:
#   - AWS credentials configured (aws configure)
#   - bedrock-agentcore-starter-toolkit installed (pip install bedrock-agentcore-starter-toolkit)
#   - uv installed for dependency management
#   - Gateway deployed first (bash scripts/deploy_gateway.sh) — creates Cognito
#     User Pool and M2M client needed for JWT inbound auth
#
# Usage:
#   bash scripts/deploy_mcp.sh
#
# The MCP server hosts all context tools (load_claims_workflow_context,
# load_premium_formulas_context) and, once implemented, data tools
# (get_product_info, get_claim_details).
#
# JWT Inbound Authorization:
#   The MCP runtime is configured to accept JWT tokens issued by the Cognito
#   User Pool created in deploy_gateway.sh. The Gateway authenticates to this
#   runtime using OAuth client credentials (M2M). The authorizer validates:
#     - discoveryUrl: Cognito OIDC discovery endpoint
#     - allowedClients: M2M client ID (matched against the client_id claim in
#       Cognito client_credentials tokens, which have no aud claim)
#
# After deployment, note the runtime ARN printed in the output — it is
# needed for the gateway target configuration in deploy_gateway.sh.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GATEWAY_OUTPUT_FILE="$SCRIPT_DIR/gateway_output.json"

echo "=== Deploying Sage MCP Server to AgentCore Runtime ==="
echo "Region: $REGION"
echo "Project root: $PROJECT_ROOT"
echo ""

# ── 0. Resolve Cognito details for JWT inbound authorization ─────────
# The gateway deployment (deploy_gateway.sh) creates a Cognito User Pool
# and M2M app client. We read those from gateway_output.json to configure
# JWT inbound auth on the MCP runtime.

AUTHORIZER_CONFIG_FLAG=""

if [[ -f "$GATEWAY_OUTPUT_FILE" ]]; then
  COGNITO_POOL_ID=$(jq -r '.cognitoPoolId // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)
  M2M_CLIENT_ID=$(jq -r '.cognitoM2mClientId // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)

  if [[ -n "$COGNITO_POOL_ID" && -n "$M2M_CLIENT_ID" ]]; then
    DISCOVERY_URL="https://cognito-idp.${REGION}.amazonaws.com/${COGNITO_POOL_ID}/.well-known/openid-configuration"
    AUTHORIZER_JSON="{\"customJWTAuthorizer\":{\"discoveryUrl\":\"${DISCOVERY_URL}\",\"allowedClients\":[\"${M2M_CLIENT_ID}\"]}}"
    AUTHORIZER_CONFIG_FLAG="--authorizer-config ${AUTHORIZER_JSON}"
    echo "Step 0: JWT inbound authorization enabled"
    echo "  Cognito Pool ID: $COGNITO_POOL_ID"
    echo "  M2M Client ID:   $M2M_CLIENT_ID"
    echo "  Discovery URL:   $DISCOVERY_URL"
  else
    echo "Step 0: WARNING — gateway_output.json missing cognitoPoolId or cognitoM2mClientId"
    echo "  Deploying WITHOUT JWT inbound auth. Run deploy_gateway.sh first, then re-run this script."
  fi
else
  echo "Step 0: No gateway_output.json found — deploying WITHOUT JWT inbound auth."
  echo "  To enable JWT auth, run deploy_gateway.sh first, then re-run this script."
fi
echo ""

# ── 1. Configure the MCP server for AgentCore deployment ──────────────
# The entrypoint is mcp_server/server.py which exposes the FastMCP server.
# agentcore configure sets up .bedrock_agentcore.yaml with the correct
# entrypoint, port, request header allowlist, and JWT authorizer config.

echo "Step 1: Configuring MCP server for AgentCore deployment..."
# shellcheck disable=SC2086
uv run agentcore configure \
  --non-interactive \
  --name sage_mcp_server \
  -e mcp_server/server.py \
  --protocol MCP \
  --deployment-type direct_code_deploy \
  --runtime PYTHON_3_13 \
  --region "$REGION" \
  --request-header-allowlist "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id" \
  --disable-otel \
  --disable-memory \
  $AUTHORIZER_CONFIG_FLAG

# ── 2. Deploy to AgentCore Runtime ────────────────────────────────────
# agentcore launch packages the code as a zip, uploads to S3, and deploys
# to AgentCore Runtime. The first deployment installs dependencies and
# takes longer; subsequent deploys reuse cached dependencies.

echo ""
echo "Step 2: Deploying MCP server to AgentCore Runtime..."
uv run agentcore launch

echo ""
echo "=== MCP Server deployment complete ==="
if [[ -n "${AUTHORIZER_CONFIG_FLAG:-}" ]]; then
  echo "  JWT inbound authorization: ENABLED"
  echo "  The MCP runtime will only accept tokens from the Cognito User Pool."
else
  echo "  JWT inbound authorization: DISABLED (no gateway_output.json)"
fi
echo ""
echo "Next steps:"
if [[ -z "${AUTHORIZER_CONFIG_FLAG:-}" ]]; then
  echo "  1. Run: bash scripts/deploy_gateway.sh"
  echo "  2. Re-run: bash scripts/deploy_mcp.sh  (to enable JWT inbound auth)"
  echo "  3. Run: bash scripts/deploy_agent.sh"
else
  echo "  1. Note the runtime ARN from the output above"
  echo "  2. Run: bash scripts/deploy_agent.sh"
fi
