#!/usr/bin/env bash
# Configure and deploy the shared Sage agent once per fixed tenant lane.
# Use --render to validate and print configuration without calling AgentCore.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IDENTITY_CONFIG_FILE="${SAGE_IDENTITY_CONFIG_FILE:-$SCRIPT_DIR/identity_deployment.json}"
REGISTRY_OUTPUT_FILE="${REGISTRY_OUTPUT_FILE:-$SCRIPT_DIR/registry_output.json}"
MODE="${1:-deploy}"

if [[ "$MODE" != "deploy" && "$MODE" != "--render" ]]; then
  echo "Usage: bash scripts/deploy_agent.sh [--render]" >&2
  exit 2
fi

cd "$PROJECT_ROOT"
RENDERED_CONFIG="$(uv run python -m scripts.render_identity_deployments \
  --config "$IDENTITY_CONFIG_FILE" \
  --component agent)"

if [[ "$MODE" == "--render" ]]; then
  printf '%s\n' "$RENDERED_CONFIG"
  exit 0
fi

if [[ ! -f "$REGISTRY_OUTPUT_FILE" ]]; then
  echo "registry_output.json is required to preserve dynamic skills" >&2
  exit 1
fi
SKILL_REGISTRY_ID="$(jq -r '.registryId // empty' "$REGISTRY_OUTPUT_FILE")"
if [[ -z "$SKILL_REGISTRY_ID" ]]; then
  echo "registryId is required to preserve dynamic skills" >&2
  exit 1
fi

echo "=== Deploying Sage Agent to two isolated tenant lanes ==="
echo "Region: $REGION"

while IFS= read -r lane; do
  LANE_ID="$(jq -r '.laneId' <<<"$lane")"
  RUNTIME_NAME="$(jq -r '.runtimeName' <<<"$lane")"
  AUTHORIZER_CONFIG="$(jq -c '.authorizerConfig' <<<"$lane")"
  HEADER_ALLOWLIST="$(jq -r '.requestHeaderAllowlist | join(",")' <<<"$lane")"
  GATEWAY_URL="$(jq -r '.environment.GATEWAY_URL' <<<"$lane")"

  echo "Configuring $RUNTIME_NAME for $LANE_ID"
  uv run agentcore configure \
    --non-interactive \
    --name "$RUNTIME_NAME" \
    -e agent/agent.py \
    --protocol HTTP \
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
    --env "GATEWAY_URL=$GATEWAY_URL" \
    --env "SKILL_REGISTRY_ID=$SKILL_REGISTRY_ID"
done < <(jq -c '.[]' <<<"$RENDERED_CONFIG")

echo "=== Two-lane Agent deployment complete ==="
