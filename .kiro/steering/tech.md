---
inclusion: always
---

# Tech Stack and Development Conventions

## Backend

- Python 3.13+
- Strands Agents and `BedrockAgentCoreApp`
- FastMCP on port 8000 with streamable HTTP
- AgentCore Runtime for Agent and MCP hosting
- AgentCore Gateway HTTP MCP passthrough with `JWT_PASSTHROUGH`
- PyJWT with cryptography for independent Sage API validation
- `uv` with `pyproject.toml` and `uv.lock`

### Python conventions

- Use type hints and focused docstrings on public boundaries.
- Keep model orchestration in `agent/`, MCP transport/tool registration in `mcp_server/`, shared API authorization/data in `sage_api/`, and cross-component identity primitives in `sage_identity/`.
- Use `headers: dict = CurrentHeaders()` for FastMCP request headers.
- Parse exactly one Authorization bearer at each code-owned forwarding boundary and preserve its bytes.
- Do not put architecture route names into implementation identifiers.
- Do not add dependencies when the standard library or an installed package already covers the need.

## Frontend

- React, TypeScript strict mode, Vite, Tailwind CSS, shadcn/ui
- `amazon-cognito-identity-js` for tenant-specific browser authentication
- Direct streaming to the selected Agent Runtime endpoint

### Frontend conventions

- Trusted lane configuration contains exactly Tenant_A and Tenant_B.
- Access tokens and renewal stay inside the authentication/session layer.
- All Agent invocation transport goes through `frontend/src/lib/agentcore-client/client.ts`.
- Conversation state is bound to session, lane, subject, and tenant; identity changes clear it.
- Render model output as safe text/Markdown, never unsanitized HTML.

## Authentication responsibilities

| Component | Responsibility |
|---|---|
| Frontend | Validate lane/session claims and send the current access token |
| Managed authorizers | Verify signature, expiry, issuer, client, token type, local scope, and exact lane tenant |
| Agent application | Forward the exact bearer and correlation ID |
| MCP application | Extract subject/tenant and enforce hosting-lane equality |
| Sage API | Independently validate both issuers and enforce business/data authorization |

AgentCore Identity access-token and workload-token decorators are intentionally absent because they obtain replacement outbound credentials.

## Testing

| Layer | Command |
|---|---|
| Backend | `uv run pytest -q` |
| Python compile | `uv run python -m compileall -q agent mcp_server sage_api sage_identity scripts tests` |
| Frontend tests | `cd frontend && npm test` |
| Frontend build | `cd frontend && npm run build` |
| Shell syntax | `bash -n scripts/deploy_agent.sh scripts/deploy_gateway.sh scripts/deploy_mcp.sh` |

Property tests are useful for identity invariants; focused unit tests cover exact bearer transport, authorizer payloads, fail-closed parsing, and API isolation.

## Deployment

```bash
uv run python scripts/deploy_user_pool.py
uv run python scripts/deploy_registry.py
bash scripts/deploy_mcp.sh
bash scripts/deploy_gateway.sh
bash scripts/deploy_agent.sh
```

Deployment uses `scripts/identity_deployment.json` or `SAGE_IDENTITY_CONFIG_FILE`. Rendering and dry-run planning are mutation-free; deploy commands require explicit operator intent and approved AWS configuration.
