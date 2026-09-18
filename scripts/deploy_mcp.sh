#!/usr/bin/env bash
# Configure and deploy the shared Sage MCP server once per fixed tenant lane.
# Use --render to validate and print configuration without calling AgentCore.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IDENTITY_CONFIG_FILE="${SAGE_IDENTITY_CONFIG_FILE:-$SCRIPT_DIR/identity_deployment.json}"
MODE="${1:-deploy}"

if [[ "$MODE" != "deploy" && "$MODE" != "--render" ]]; then
  echo "Usage: bash scripts/deploy_mcp.sh [--render]" >&2
  exit 2
fi

cd "$PROJECT_ROOT"
RENDERED_CONFIG="$(uv run python -m scripts.render_identity_deployments \
  --config "$IDENTITY_CONFIG_FILE" \
  --component mcp)"

if [[ "$MODE" == "--render" ]]; then
  printf '%s\n' "$RENDERED_CONFIG"
  exit 0
fi

SAGE_API_URL="${SAGE_API_URL:?Set SAGE_API_URL to the configured shared Sage API endpoint}"

echo "=== Deploying Sage MCP Server to two isolated tenant lanes ==="
echo "Region: $REGION"

while IFS= read -r lane; do
  LANE_ID="$(jq -r '.laneId' <<<"$lane")"
  RUNTIME_NAME="$(jq -r '.runtimeName' <<<"$lane")"
  AUTHORIZER_CONFIG="$(jq -c '.authorizerConfig' <<<"$lane")"
  HEADER_ALLOWLIST="$(jq -r '.requestHeaderAllowlist | join(",")' <<<"$lane")"
  EXPECTED_TENANT="$(jq -r '.environment.SAGE_EXPECTED_TENANT' <<<"$lane")"
  CANONICAL_CLAIM="$(jq -r '.environment.SAGE_CANONICAL_TENANT_CLAIM' <<<"$lane")"
  SOURCE_CLASSIFICATION="$(jq -r '.sourceSignalControl.classification' <<<"$lane")"

  echo "Configuring $RUNTIME_NAME for $LANE_ID (Gateway source control: $SOURCE_CLASSIFICATION)"
  uv run agentcore configure \
    --non-interactive \
    --name "$RUNTIME_NAME" \
    -e mcp_server/server.py \
    --protocol MCP \
    --deployment-type direct_code_deploy \
    --runtime PYTHON_3_13 \
    --region "$REGION" \
    --request-header-allowlist "$HEADER_ALLOWLIST" \
    --authorizer-config "$AUTHORIZER_CONFIG" \
    --disable-otel \
    --disable-memory

  echo "Launching $RUNTIME_NAME"
  uv run agentcore launch \
    --agent "$RUNTIME_NAME" \
    --env "SAGE_LANE_ID=$LANE_ID" \
    --env "SAGE_EXPECTED_TENANT=$EXPECTED_TENANT" \
    --env "SAGE_CANONICAL_TENANT_CLAIM=$CANONICAL_CLAIM" \
    --env "SAGE_API_URL=$SAGE_API_URL"
done < <(jq -c '.[]' <<<"$RENDERED_CONFIG")

echo "=== Two-lane MCP deployment complete ==="
