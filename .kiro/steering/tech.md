---
inclusion: always
---

# Tech Stack & Development Conventions

## Backend — Python

- **Runtime**: Python 3.11+
- **Agent framework**: Strands SDK for orchestration with tool use
- **Agent server**: BedrockAgentCoreApp SDK (`bedrock-agentcore`) — handles `/invocations`, `/ping`, streaming, port 8080 automatically
- **MCP server**: FastMCP with decorator-based tool registration (`@mcp.tool()`), runs on port 8000 with `stateless_http=True`
- **Foundation model**: Amazon Bedrock — Claude Sonnet 4.5
- **Hosting**: AgentCore Runtime (agent + MCP server), AgentCore Gateway (semantic routing)
- **Auth**: Two Cognito pools — `sage-tenant-pool` for user ID tokens (Phase 2, `allowedAudience` on agent runtime) and `sage-mcp-pool` for M2M tokens (Gateway→MCP, `allowedClients` on MCP runtime). Phase 1 fallback uses M2M token directly from frontend.

### Python code style

- Type hints on all function signatures
- Docstrings on public functions (Google style)
- Tool functions must include a descriptive docstring — AgentCore Gateway uses it for semantic routing
- No domain logic in the agent layer; agent code is orchestration only
- Tenant ID comes from the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header — never from user input or hardcoded values
- Data tools must use `headers: dict = CurrentHeaders()` (from `fastmcp.dependencies`) to receive injected HTTP headers — never `headers: dict | None = None`
- MCP server runs on port 8000 (not 8080) with `stateless_http=True` passed to `mcp.run()`

## Frontend — TypeScript / React

- **UI framework**: React 18+ with functional components and hooks
- **Build tool**: Vite
- **Styling**: Tailwind CSS + shadcn/ui components
- **Streaming**: Custom AgentCore Client (adapted from FAST) — direct SSE from BedrockAgentCoreApp `/invocations`
- **Language**: TypeScript in strict mode
- **Hosting**: AWS Amplify Hosting (demo)

### TypeScript code style

- Prefer `interface` over `type` for object shapes
- Use named exports
- All agent communication goes through `frontend/src/lib/agentcore-client/client.ts` — this is the single point where the tenant header is injected
- When `tenantId` changes, the conversation must be cleared via `useEffect` dependency on `tenantId` in `ChatInterface.tsx`

## Testing

| Layer | Framework | Style |
|-------|-----------|-------|
| Backend | pytest + Hypothesis | Property-based tests for business logic, unit tests for tools |
| Frontend | Jest/Vitest + fast-check | Property-based tests for data transforms, component tests for UI |

- Property-based tests are the preferred approach for validating business rules (premium calculations, data filtering, tenant isolation)
- Use `@given` (Hypothesis) and `fc.property` (fast-check) for invariant checks
- Unit tests cover tool registration, header parsing, and API contract validation

## Common Commands

```bash
# Initialize Python project (first time)
uv init
uv venv
source .venv/bin/activate

# Add Python dependencies
uv add strands-agents bedrock-agentcore fastmcp

# Add dev dependencies
uv add --dev hypothesis pytest

# Run MCP server locally
uv run python mcp_server/server.py

# Run agent locally
uv run python agent/agent.py

# Frontend dev
cd frontend && npm install && npm run dev

# Run backend tests
uv run pytest

# Run frontend tests
cd frontend && npm test

# Deploy (order matters: Gateway → MCP → Agent)
uv run python scripts/deploy_gateway.py   # or: bash scripts/deploy_gateway.sh
bash scripts/deploy_mcp.sh
bash scripts/deploy_agent.sh

# Get a fresh bearer token (auto-updates frontend/.env.local)
uv run python scripts/get_token.py
```

## Dependency management

- Backend: `uv` with `pyproject.toml` and `uv.lock` at project root — managed via `uv add`/`uv remove`
- Frontend: `package.json` in `frontend/` — managed via `npm`
- No monorepo tooling; backend and frontend are managed independently
