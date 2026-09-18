# Sage AI Assistant

Sage is a two-tenant insurance assistant built on Amazon Bedrock AgentCore. Tenant_A and Tenant_B are internal security identifiers; AXA and Allianz are display names only.

## Architecture

```text
React frontend
  -> tenant-specific Cognito user pool (access JWT)
  -> tenant-specific Agent Runtime
  -> tenant-specific AgentCore Gateway
  -> tenant-specific MCP Runtime
  -> shared Sage API
  -> tenant-isolated data
```

The original Cognito user access token is the only bearer in this chain. AgentCore managed custom JWT authorizers at Agent Runtime, Gateway, and MCP Runtime validate the lane discovery URL, client, local scope, `token_use=access`, and `custom:tenant_id`. Application code preserves the bearer, extracts the already-validated subject and tenant for same-lane binding, and performs business authorization.

The shared Sage API is the final data boundary. It independently validates signatures, issuer, expiry, client, read scope, subject, and tenant against an exact two-issuer allowlist before reading tenant data.

There is no M2M, OAuth credential-provider, token exchange, OBO, workload-token, context-token, static-bearer, or server-side renewal fallback. Browser renewal stays in the selected tenant pool.

## Repository layout

```text
agent/                         AgentCore Runtime entrypoint and prompt
frontend/                      React/Vite browser application
mcp_server/                    FastMCP server, request identity, Sage API client
sage_api/                      Shared validation, authorization, and tenant data boundary
sage_identity/                 Shared identity models, managed authorizers, transport,
                               Cognito customization, and deployment evidence
scripts/                       Registry, Cognito, runtime, Gateway, and dry-run tooling
skills/                        Agent Skills loaded from AgentCore Registry
tests/                         Focused backend tests
```

`sage_identity/` is organized by responsibility. JWT-passthrough route names belong in architecture documentation, not implementation package or identifier names.

## Identity boundaries

| Boundary | Responsibility |
|---|---|
| Frontend | Select one trusted lane, authenticate, retain renewal material, send the exact access token |
| Agent Runtime | Managed JWT validation for `sage-agent/invoke` and the lane tenant |
| Agent application | Preserve the exact bearer and correlation ID; invoke only its configured Gateway |
| Gateway | Managed JWT validation for `sage-gateway/invoke`; forward via `JWT_PASSTHROUGH` |
| MCP Runtime | Managed JWT validation for `sage-mcp/invoke` and the lane tenant |
| MCP application | Extract one subject and tenant, bind to the hosting lane, forward the exact bearer |
| Sage API | Independently validate the JWT and enforce subject, tenant, source, and data isolation |

## Demo capabilities

- Skills: `claims-workflow`, `premium-formulas`
- MCP tools: `get_product_info`, `get_claim_details`
- Demo display names: AXA for Tenant_A, Allianz for Tenant_B
- Data source: `sage_api/mock_data.py`, reachable only through the Sage API

## Local development

Requirements: Python 3.13+, `uv`, Node.js 20+, and npm.

```bash
# Backend
uv sync
uv run pytest -q

# MCP server
uv run python mcp_server/server.py

# Shared Sage API
uv run python -m sage_api.http

# Frontend
cd frontend
npm install
npm test
npm run dev
```

The agent requires `SKILL_REGISTRY_ID` and `GATEWAY_URL`; it loads approved skills from AgentCore Registry at startup.

## Deployment configuration

Deployment scripts consume `scripts/identity_deployment.json` or the path in `SAGE_IDENTITY_CONFIG_FILE`. No cloud mutation is performed by the renderer or dry-run planner.

Recommended order after configuration and security approval:

```bash
uv run python scripts/deploy_user_pool.py
uv run python scripts/deploy_registry.py
bash scripts/deploy_mcp.sh
bash scripts/deploy_gateway.sh
bash scripts/deploy_agent.sh
```

Useful read-only commands:

```bash
uv run python -m scripts.render_identity_deployments \
  --config scripts/identity_deployment.json --component agent

uv run python scripts/deploy_gateway.py \
  --config scripts/identity_deployment.json --render

uv run python scripts/plan_identity_deployment.py \
  --manifest scripts/identity_deployment.json
```

No deployment command should run until the two lane records, inactive candidate resources, rollback references, issuer/client/scope bindings, and shared API source controls have been reviewed.

## Environment variables

### Frontend

Each tenant has its own values:

- `VITE_TENANT_A_USER_POOL_ID`, `VITE_TENANT_B_USER_POOL_ID`
- `VITE_TENANT_A_APP_CLIENT_ID`, `VITE_TENANT_B_APP_CLIENT_ID`
- `VITE_TENANT_A_ISSUER`, `VITE_TENANT_B_ISSUER`
- `VITE_TENANT_A_AGENT_RUNTIME_ENDPOINT`, `VITE_TENANT_B_AGENT_RUNTIME_ENDPOINT`

### Cognito pre-token Lambda

Each lane's Cognito trigger must reference a qualified Lambda alias/version whose
handler is `sage_identity.cognito.lambda_handler`. The deployment preflight
requires `<TENANT>_PRE_TOKEN_LAMBDA_ARN` and
`<TENANT>_PRE_TOKEN_LAMBDA_CODE_SHA256`, and verifies the function's
`SAGE_TOKEN_CUSTOMIZER_CONFIG` JSON against the pool, tenant, assignment
attribute, clients, and grants before any Cognito mutation.

### Agent

- `GATEWAY_URL`
- `SKILL_REGISTRY_ID`

### MCP

- `SAGE_LANE_ID`
- `SAGE_EXPECTED_TENANT`
- `SAGE_CANONICAL_TENANT_CLAIM`
- `SAGE_API_URL` — HTTPS is required except for loopback local development

### Sage API

- `SAGE_API_ISSUER_MAP`
- `SAGE_API_PUBLIC_KEYS`
- `SAGE_API_APPROVED_SOURCES` — trusted source identities injected as
  `sage.source_path` by the private ingress adapter; client IP addresses and
  request headers are not accepted as source authority
- Optional: `SAGE_API_HOST` (defaults to `127.0.0.1` for local development),
  `SAGE_API_PORT`

## Verification

```bash
uv run pytest -q
uv run python -m compileall -q agent mcp_server sage_api sage_identity scripts tests
bash -n scripts/deploy_agent.sh scripts/deploy_gateway.sh scripts/deploy_mcp.sh
cd frontend && npm test && npm run build
git diff --check
```
