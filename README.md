# Sage AI Assistant

A multi-tenant, domain-aware conversational AI agent for the Insurance Suite, built on AWS Bedrock AgentCore. Sage uses a minimal base prompt (~150 tokens) combined with an AgentCore Gateway that semantically routes user queries to the right tools at runtime — no hardcoded routing logic required.

## Architecture

```
React Frontend (login screen)
    │  USER_PASSWORD_AUTH → Cognito tenant pool (sage-tenant-pool)
    │  ← ID token (custom:tenant_id = "axa" | "allianz")
    │
    │  POST /invocations
    │  Authorization: Bearer <id_token>
    ▼
AgentCore Runtime — Strands Agent (agent/agent.py)
    │  JWT authorizer: allowedAudience = [axaClientId, allianzClientId]
    │  Decodes JWT → extracts custom:tenant_id
    │  Fetches M2M token from sage-mcp-pool (client_credentials)
    │  Forwards: Authorization: Bearer <m2m_token>
    │            X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id: <tenant>
    ▼
AgentCore Gateway — Semantic routing over tool descriptions
    │  OAuth M2M (Cognito sage-mcp-pool, client_credentials)
    ▼
AgentCore Runtime — FastMCP Server (mcp_server/server.py)
    │  JWT authorizer: allowedClients = [m2mClientId]
    │  Propagates X-...-Tenant-Id header to all tools
    ├── load_claims_workflow_context  →  skills/claims_workflow.md
    ├── load_premium_formulas_context →  skills/premium_formulas.md
    ├── get_product_info              →  mcp_server/mock_data.py (filtered by tenant)
    └── get_claim_details             →  mcp_server/mock_data.py (filtered by tenant)
```

**Key design decisions:**

- Minimal base prompt — domain knowledge is injected at runtime via context tools, not baked into the prompt
- AgentCore Gateway replaces a classifier model — semantic search over tool descriptions routes queries automatically
- Tenant isolation via `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header, propagated end-to-end
- Skills are plain Markdown files — editable without code changes or redeployment
- Agent runtime: `allowedAudience` (Phase 2, user ID tokens carry `aud` = client ID) or `allowedClients` fallback (Phase 1, M2M tokens)
- MCP runtime: `allowedClients` — Gateway always uses M2M `client_credentials` tokens which carry `client_id` but no `aud` claim

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent | Strands SDK + BedrockAgentCoreApp |
| Foundation model | Claude Sonnet 4.5 via Amazon Bedrock |
| MCP server | FastMCP (Python), port 8000, `stateless_http=True` |
| Gateway | AgentCore Gateway with semantic search |
| Auth | Cognito: tenant pool (user ID tokens, Phase 2) + M2M pool (Gateway→MCP) |
| Frontend | React 18 + Vite + Tailwind CSS + shadcn/ui |
| Streaming | Direct SSE from `/invocations` (FAST pattern) |
| Runtime | Python 3.13, `uv` for dependency management |

## Project Structure

```
sage-ai-assistant/
├── agent/
│   ├── prompts/system.md       # Base prompt (~150 tokens, personality + rules only)
│   └── agent.py               # BedrockAgentCoreApp entrypoint
├── mcp_server/
│   ├── server.py               # FastMCP entry point — registers all tools
│   ├── mock_data.py            # In-memory tenant-scoped mock data
│   └── tools/
│       ├── context_tools.py    # load_* tools — read skills/ Markdown
│       └── data_tools.py       # get_* tools — tenant-scoped data
├── skills/
│   ├── claims_workflow.md      # Claims processing domain knowledge
│   └── premium_formulas.md     # Premium calculation formulas and rules
├── frontend/                   # React + Vite + Tailwind + shadcn
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── TenantSelector.tsx
│   │   │   └── ToolActivity.tsx
│   │   └── lib/agentcore-client/  # SSE streaming client
│   └── .env.local              # VITE_AGENT_URL, VITE_AGENT_BEARER_TOKEN
├── scripts/
│   ├── deploy_gateway.py       # Full gateway deployment (Cognito + Gateway + target)
│   ├── deploy_gateway.sh       # Thin wrapper for deploy_gateway.py
│   ├── deploy_mcp.sh           # Deploy MCP server to AgentCore Runtime
│   ├── deploy_agent.sh         # Deploy agent to AgentCore Runtime
│   └── get_token.py            # Fetch M2M token + auto-update frontend/.env.local
├── pyproject.toml
└── uv.lock
```

## Demo Tenants

Two tenants with isolated mock data:

| Tenant | Products | Sample Claims |
|--------|---------|---------------|
| AXA | AXA Drive Protect (motor, €850 base premium) | CLM-12345 (approved, €3,200) |
| Allianz | Allianz AutoGuard Plus (motor, €920 base premium) | CLM-5454 (under review, €8,750) |

## Tools

| Tool | Type | Description |
|------|------|-------------|
| `load_claims_workflow_context` | Context | Loads claims processing domain knowledge from `skills/claims_workflow.md` |
| `load_premium_formulas_context` | Context | Loads premium calculation rules from `skills/premium_formulas.md` |
| `get_product_info` | Data | Returns tenant-scoped product details filtered by `product_type` |
| `get_claim_details` | Data | Returns tenant-scoped claim details filtered by `claim_reference` |

Context tools (`load_*`) are stateless Markdown readers. Data tools (`get_*`) read the tenant ID from the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header via `CurrentHeaders()`.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- Node.js 20+ and npm
- AWS credentials configured (`aws configure`)
- AWS region: `us-east-1` (default)

## Local Development

### 1. Install dependencies

```bash
uv venv
source .venv/bin/activate
uv add strands-agents bedrock-agentcore fastmcp
uv add --dev hypothesis pytest bedrock-agentcore-starter-toolkit
```

### 2. Run the MCP server

```bash
uv run python mcp_server/server.py
# Starts on http://localhost:8000
```

### 3. Run the agent

```bash
uv run python agent/agent.py
# Starts on http://localhost:8080
# Falls back to stdio MCP when GATEWAY_URL is not set
```

### 4. Run the frontend

```bash
cd frontend
npm install
npm run dev
# Opens on http://localhost:5173
# Proxies /invocations to http://localhost:8080
```

## Deployment to AWS

Deploy in this order — each step depends on the previous.

### Step 1 — Deploy the Gateway

Creates the Cognito User Pool, resource server, M2M app client, AgentCore credential provider, gateway, and MCP target. Saves all outputs to `scripts/gateway_output.json`.

```bash
bash scripts/deploy_gateway.sh
# or: uv run python scripts/deploy_gateway.py
```

### Step 2 — Deploy the MCP Server

Packages and deploys the FastMCP server to AgentCore Runtime with JWT inbound authorization (reads Cognito details from `gateway_output.json`).

```bash
bash scripts/deploy_mcp.sh
```

### Step 3 — Deploy the Agent

Packages and deploys the Strands agent to AgentCore Runtime. Injects `GATEWAY_URL` and Cognito auth credentials as environment variables.

```bash
bash scripts/deploy_agent.sh
```

### Step 4 — Get a bearer token (Phase 1 only)

Only needed when running without Cognito login (`VITE_COGNITO_*` vars not set). In Phase 2, users authenticate directly — skip this step.

```bash
uv run python scripts/get_token.py
```

### Step 5 — Start the frontend

```bash
cd frontend && npm run dev
```

For production, deploy the frontend to AWS Amplify Hosting.

## Authentication Flow

Two separate Cognito pools, two token types:

```
# Phase 2 (active): user login
React (login) ──(USER_PASSWORD_AUTH)──► Cognito tenant pool (sage-tenant-pool)
                                              │ ID token (custom:tenant_id)
                                              ▼
React (chat) ──(Authorization: Bearer <id_token>)──► Agent Runtime
                                                           │ allowedAudience = [axaClientId, allianzClientId]
                                                           │ decode JWT → extract custom:tenant_id
                                                           ▼
                                                    AgentCore Gateway
                                                           │ OAuth M2M (client_credentials)
                                                           ▼
                                                     MCP Runtime (allowedClients = [m2mClientId])
                                                     filters data by tenant_id header
```

- Agent runtime: `allowedAudience` — ID tokens carry `aud` = client ID
- MCP runtime: `allowedClients` — M2M tokens carry `client_id`, no `aud`
- Phase 1 fallback: set `VITE_AGENT_BEARER_TOKEN` (M2M token), leave `VITE_COGNITO_*` vars empty → frontend shows tenant dropdown instead of login screen

## Adding New Capabilities

**New domain knowledge** (workflows, formulas, rules):
1. Create `skills/<topic>.md` with the domain content
2. Add a `load_<topic>_context` tool in `mcp_server/tools/context_tools.py`
3. Write a descriptive tool description — the Gateway uses it for semantic routing

**New tenant-scoped data**:
1. Add data to `mcp_server/mock_data.py` keyed by tenant ID
2. Add a `get_<entity>` tool in `mcp_server/tools/data_tools.py`
3. Use `headers: dict = CurrentHeaders()` to read the tenant header

No changes to the base prompt, gateway config, or existing tools required.

## Running Tests

```bash
# Backend
uv run pytest

# Frontend
cd frontend && npm test
```

## Environment Variables

### Frontend (`frontend/.env.local`)

| Variable | Description |
|----------|-------------|
| `VITE_AGENT_URL` | AgentCore agent runtime `/invocations` URL |
| `VITE_AGENT_BEARER_TOKEN` | M2M bearer token (refresh with `get_token.py`) |

### Agent (set by `deploy_agent.sh`)

| Variable | Description |
|----------|-------------|
| `GATEWAY_URL` | AgentCore Gateway MCP endpoint URL |
| `GATEWAY_AUTH_TOKEN_ENDPOINT` | Cognito token endpoint |
| `GATEWAY_AUTH_CLIENT_ID` | Cognito M2M client ID |
| `GATEWAY_AUTH_CLIENT_SECRET` | Cognito M2M client secret |
| `GATEWAY_AUTH_SCOPE` | OAuth scope (`sage-mcp/tools`) |

## Phase 2: JWT Tenant Authentication (Active)

Phase 2 is the current active mode. Users log in via Cognito and the ID token carries their tenant identity — no static bearer token needed.

### Setup (already deployed)

```bash
# 1. Create the tenant user pool (sage-tenant-pool) with AXA + Allianz app clients
uv run python scripts/deploy_user_pool.py
# Saves outputs to scripts/user_pool_output.json

# 2. Redeploy the agent with Phase 2 JWT inbound auth
#    (reads user_pool_output.json, configures allowedAudience for both tenant clients)
bash scripts/deploy_agent.sh

# 3. Set frontend/.env.local with Cognito client IDs (from user_pool_output.json)
# VITE_COGNITO_USER_POOL_ID=<userPoolId>
# VITE_COGNITO_AXA_CLIENT_ID=<axaClientId>
# VITE_COGNITO_ALLIANZ_CLIENT_ID=<allianzClientId>
# VITE_COGNITO_DOMAIN=<cognitoHostedUiDomain>
```

When all four `VITE_COGNITO_*` variables are set, the frontend shows a login screen instead of the tenant dropdown and sends the Cognito ID token as `Authorization: Bearer` on every request.

### Frontend environment variables (Phase 2)

| Variable | Description |
|----------|-------------|
| `VITE_COGNITO_USER_POOL_ID` | Cognito User Pool ID from `user_pool_output.json` |
| `VITE_COGNITO_AXA_CLIENT_ID` | AXA app client ID from `user_pool_output.json` |
| `VITE_COGNITO_ALLIANZ_CLIENT_ID` | Allianz app client ID from `user_pool_output.json` |
| `VITE_COGNITO_DOMAIN` | Cognito hosted UI domain (not required for direct auth) |

### Demo credentials

| Tenant | Username | Password |
|--------|----------|----------|
| AXA | `axa-user` | `AXApassword1` |
| Allianz | `allianz-user` | `Allianzpassword1` |
