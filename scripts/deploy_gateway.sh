#!/usr/bin/env bash
# Apply each lane's managed JWT authorizer and deploy its HTTP MCP passthrough target.
# This is a thin wrapper around scripts/deploy_gateway.py.
#
# Usage:
#   bash scripts/deploy_gateway.sh
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run python "$SCRIPT_DIR/deploy_gateway.py" "$@"
