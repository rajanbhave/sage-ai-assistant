#!/usr/bin/env bash
# Deploy the AgentCore Gateway with Cognito OAuth M2M authentication.
# This is a thin wrapper around scripts/deploy_gateway.py.
#
# Usage:
#   bash scripts/deploy_gateway.sh
#
# Environment variables (optional overrides):
#   AWS_REGION          — defaults to us-east-1
#   MCP_RUNTIME_ARN     — MCP server runtime ARN (auto-detected from .bedrock_agentcore.yaml)
#   GATEWAY_NAME        — gateway name prefix (defaults to sage-gateway)
#   COGNITO_POOL_NAME   — Cognito User Pool name (defaults to sage-mcp-pool)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run python "$SCRIPT_DIR/deploy_gateway.py" "$@"
