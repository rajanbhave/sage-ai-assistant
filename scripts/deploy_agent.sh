#!/usr/bin/env bash
# Deploy the Sage Strands agent to AgentCore Runtime.
#
# Prerequisites:
#   - AWS credentials configured
#   - bedrock-agentcore-starter-toolkit installed
#   - MCP server deployed (deploy_mcp.sh)
#   - Gateway deployed (deploy_gateway.sh)
#
# Usage:
#   bash scripts/deploy_agent.sh
#
# The BedrockAgentCoreApp SDK automatically exposes:
#   - POST /invocations  (agent entrypoint)
#   - GET  /ping          (health check)
#   - Port 8080
#
# After deployment, note the agent runtime ARN — use it to obtain a
# bearer token for the frontend:
#   agentcore identity get-cognito-inbound-token

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GATEWAY_OUTPUT_FILE="$SCRIPT_DIR/gateway_output.json"
REGISTRY_OUTPUT_FILE="$SCRIPT_DIR/registry_output.json"

echo "=== Deploying Sage Agent to AgentCore Runtime ==="
echo "Region: $REGION"
echo "Project root: $PROJECT_ROOT"
echo ""

# ── 0. Resolve Cognito details for JWT inbound authorization ─────────
# Phase 2: prefer the tenant user pool (user_pool_output.json) which
# issues per-tenant JWTs with custom:tenant_id claims.
# Phase 1 fallback: use the M2M pool from gateway_output.json.
#
# Token type matters for the correct validator field:
#   - User ID tokens (USER_SRP_AUTH): carry `aud` = client ID → use allowedAudience
#   - M2M tokens (client_credentials): carry `client_id`, no `aud` → use allowedClients

USER_POOL_OUTPUT_FILE="$SCRIPT_DIR/user_pool_output.json"
AUTHORIZER_CONFIG_FLAG=""

if [[ -f "$USER_POOL_OUTPUT_FILE" ]]; then
  # Phase 2: tenant user pool — ID tokens use allowedAudience (aud claim = client ID)
  COGNITO_POOL_ID=$(jq -r '.userPoolId // empty' "$USER_POOL_OUTPUT_FILE" 2>/dev/null || true)
  AXA_CLIENT_ID=$(jq -r '.axaClientId // empty' "$USER_POOL_OUTPUT_FILE" 2>/dev/null || true)
  ALLIANZ_CLIENT_ID=$(jq -r '.allianzClientId // empty' "$USER_POOL_OUTPUT_FILE" 2>/dev/null || true)

  if [[ -n "$COGNITO_POOL_ID" && -n "$AXA_CLIENT_ID" && -n "$ALLIANZ_CLIENT_ID" ]]; then
    DISCOVERY_URL="https://cognito-idp.${REGION}.amazonaws.com/${COGNITO_POOL_ID}/.well-known/openid-configuration"
    # User ID tokens carry aud = client_id, so use allowedAudience (not allowedClients)
    AUTHORIZER_JSON="{\"customJWTAuthorizer\":{\"discoveryUrl\":\"${DISCOVERY_URL}\",\"allowedAudience\":[\"${AXA_CLIENT_ID}\",\"${ALLIANZ_CLIENT_ID}\"]}}"
    AUTHORIZER_CONFIG_FLAG="--authorizer-config ${AUTHORIZER_JSON}"
    echo "Step 0: Phase 2 JWT inbound authorization enabled (tenant user pool)"
    echo "  Cognito Pool ID:   $COGNITO_POOL_ID"
    echo "  AXA Client ID:     $AXA_CLIENT_ID"
    echo "  Allianz Client ID: $ALLIANZ_CLIENT_ID"
    echo "  Discovery URL:     $DISCOVERY_URL"
  else
    echo "Step 0: WARNING — user_pool_output.json missing required fields"
    echo "  Falling back to Phase 1 M2M pool..."
  fi
fi

# Phase 1 fallback: use M2M client from gateway_output.json
if [[ -z "$AUTHORIZER_CONFIG_FLAG" && -f "$GATEWAY_OUTPUT_FILE" ]]; then
  COGNITO_POOL_ID=$(jq -r '.cognitoPoolId // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)
  M2M_CLIENT_ID=$(jq -r '.cognitoM2mClientId // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)

  if [[ -n "$COGNITO_POOL_ID" && -n "$M2M_CLIENT_ID" ]]; then
    DISCOVERY_URL="https://cognito-idp.${REGION}.amazonaws.com/${COGNITO_POOL_ID}/.well-known/openid-configuration"
    AUTHORIZER_JSON="{\"customJWTAuthorizer\":{\"discoveryUrl\":\"${DISCOVERY_URL}\",\"allowedClients\":[\"${M2M_CLIENT_ID}\"]}}"
    AUTHORIZER_CONFIG_FLAG="--authorizer-config ${AUTHORIZER_JSON}"
    echo "Step 0: Phase 1 JWT inbound authorization enabled (M2M pool)"
    echo "  Cognito Pool ID: $COGNITO_POOL_ID"
    echo "  Discovery URL:   $DISCOVERY_URL"
  else
    echo "Step 0: WARNING — gateway_output.json missing Cognito details"
    echo "  Deploying WITHOUT JWT inbound auth."
  fi
fi

if [[ -z "$AUTHORIZER_CONFIG_FLAG" ]]; then
  echo "Step 0: No Cognito output files found — deploying WITHOUT JWT inbound auth."
fi
echo ""

# ── 1. Resolve Gateway URL + auth credentials (unified Cognito pool) ──
GATEWAY_URL=""
GATEWAY_AUTH_TOKEN_ENDPOINT=""
GATEWAY_AUTH_CLIENT_ID=""
GATEWAY_AUTH_CLIENT_SECRET=""
GATEWAY_AUTH_SCOPE=""
SKILL_REGISTRY_ID=""

if [[ -f "$GATEWAY_OUTPUT_FILE" ]]; then
  GATEWAY_URL=$(jq -r '.gatewayUrl // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)
  # Unified pool — same credentials used by frontend and MCP server
  GATEWAY_AUTH_TOKEN_ENDPOINT=$(jq -r '.cognitoTokenEndpoint // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)
  GATEWAY_AUTH_CLIENT_ID=$(jq -r '.cognitoM2mClientId // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)
  GATEWAY_AUTH_CLIENT_SECRET=$(jq -r '.cognitoM2mClientSecret // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)
  GATEWAY_AUTH_SCOPE=$(jq -r '.cognitoScope // empty' "$GATEWAY_OUTPUT_FILE" 2>/dev/null || true)
fi

if [[ -f "$REGISTRY_OUTPUT_FILE" ]]; then
  SKILL_REGISTRY_ID=$(jq -r '.registryId // empty' "$REGISTRY_OUTPUT_FILE" 2>/dev/null || true)
fi

if [[ -n "$GATEWAY_URL" ]]; then
  echo "Step 1: Gateway URL:            $GATEWAY_URL"
  echo "        Auth token endpoint:    $GATEWAY_AUTH_TOKEN_ENDPOINT"
  echo "        Auth client ID:         $GATEWAY_AUTH_CLIENT_ID"
  echo "        Auth scope:             $GATEWAY_AUTH_SCOPE"
else
  echo "Step 1: WARNING — no gatewayUrl in gateway_output.json; agent will use stdio fallback"
fi

if [[ -n "$SKILL_REGISTRY_ID" ]]; then
  echo "        Skill Registry ID:      $SKILL_REGISTRY_ID"
else
  echo "        WARNING — no registryId in registry_output.json; agent will fail to start"
fi
echo ""

# ── 2. Configure the agent for AgentCore deployment ───────────────────
# The entrypoint is agent/agent.py which uses BedrockAgentCoreApp.
# The SDK handles /invocations, /ping, and port 8080 automatically.
# We allowlist the tenant header so it's accessible via RequestContext.

echo "Step 2: Configuring agent for AgentCore deployment..."
# shellcheck disable=SC2086
uv run agentcore configure \
  --non-interactive \
  --name sage_agent \
  -e agent/agent.py \
  --protocol HTTP \
  --deployment-type direct_code_deploy \
  --runtime PYTHON_3_13 \
  --region "$REGION" \
  --request-header-allowlist "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id" \
  --disable-otel \
  --disable-memory \
  $AUTHORIZER_CONFIG_FLAG

# ── 3. Deploy to AgentCore Runtime ────────────────────────────────────
echo ""
echo "Step 3: Deploying agent to AgentCore Runtime..."
ENV_FLAGS=()
if [[ -n "$GATEWAY_URL" ]]; then
  ENV_FLAGS+=(--env "GATEWAY_URL=${GATEWAY_URL}")
  ENV_FLAGS+=(--env "GATEWAY_AUTH_TOKEN_ENDPOINT=${GATEWAY_AUTH_TOKEN_ENDPOINT}")
  ENV_FLAGS+=(--env "GATEWAY_AUTH_CLIENT_ID=${GATEWAY_AUTH_CLIENT_ID}")
  ENV_FLAGS+=(--env "GATEWAY_AUTH_CLIENT_SECRET=${GATEWAY_AUTH_CLIENT_SECRET}")
  ENV_FLAGS+=(--env "GATEWAY_AUTH_SCOPE=${GATEWAY_AUTH_SCOPE}")
fi
if [[ -n "$SKILL_REGISTRY_ID" ]]; then
  ENV_FLAGS+=(--env "SKILL_REGISTRY_ID=${SKILL_REGISTRY_ID}")
fi
uv run agentcore launch ${ENV_FLAGS[@]+"${ENV_FLAGS[@]}"}

echo ""
echo "=== Agent deployment complete ==="
echo ""
echo "Architecture: Frontend → Agent (AgentCore) → Gateway (AgentCore) → MCP Server (AgentCore)"
echo ""
echo "Next steps:"
echo "  1. Get a fresh M2M bearer token and auto-update frontend/.env.local:"
echo "     uv run python scripts/get_token.py"
echo "  2. Start the frontend:"
echo "     cd frontend && npm run dev"
