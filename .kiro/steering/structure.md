---
inclusion: always
---

# Project Structure

```
sage-ai-assistant/
├── agent/
│   ├── prompts/
│   │   └── system.md           # Base prompt (~150 tokens, personality + rules only)
│   └── agent.py               # BedrockAgentCoreApp entrypoint (agent + server combined)
├── mcp_server/
│   ├── server.py               # FastMCP entry point — registers all tools
│   ├── mock_data.py            # In-memory tenant-scoped mock data (keyed by tenant ID)
│   └── tools/
│       ├── context_tools.py    # load_* tools — read skills/ Markdown into context
│       └── data_tools.py       # get_* tools — return tenant-scoped data
├── skills/
│   ├── claims_workflow.md      # Claims processing domain knowledge
│   └── premium_formulas.md     # Premium calculation formulas and rules
├── frontend/                   # React + Vite + Tailwind + shadcn app
│   ├── src/
│   │   ├── App.tsx             # Root component: tenant selector + chat interface
│   │   ├── main.tsx            # Vite entry point
│   │   ├── components/
│   │   │   ├── ChatInterface.tsx  # Chat container: message list + input + streaming
│   │   │   ├── ChatMessage.tsx    # Single message: markdown + inline tool calls
│   │   │   ├── TenantSelector.tsx # Dropdown for AXA/Allianz
│   │   │   └── ToolActivity.tsx   # Inline tool call display (name, input, result)
│   │   └── lib/
│   │       └── agentcore-client/  # SSE streaming client (adapted from FAST)
│   │           ├── client.ts      # invokeAgent() — POST + SSE reader + tenant header
│   │           ├── types.ts       # StreamEvent, ChunkParser, StreamCallback
│   │           ├── parsers/
│   │           │   └── strands.ts # Strands SSE event parser
│   │           └── utils/
│   │               └── sse.ts     # readSSEStream() — generic SSE line reader
│   ├── .env.local              # VITE_AGENT_URL, VITE_AGENT_BEARER_TOKEN
│   ├── vite.config.ts          # Vite config with proxy for local dev
│   ├── index.html              # Vite entry point
│   ├── components.json         # shadcn/ui configuration
│   └── package.json
├── scripts/
│   ├── deploy_gateway.sh       # Thin wrapper — calls deploy_gateway.py
│   ├── deploy_gateway.py       # Full gateway deployment: Cognito pool, domain, resource server, M2M client, credential provider, gateway, target
│   ├── deploy_mcp.sh           # Deploy MCP server to AgentCore Runtime with JWT inbound auth
│   ├── deploy_agent.sh         # Deploy Strands agent to AgentCore Runtime with JWT inbound auth
│   ├── get_token.py            # Get M2M bearer token from Cognito and auto-update frontend/.env.local
│   ├── gateway_output.json     # Saved deployment outputs (ARNs, IDs, Cognito details)
│   └── gateway_config.json     # Gateway configuration reference
├── pyproject.toml
├── uv.lock
└── README.md
```

## Architecture Layers

| Layer | Directory | Responsibility |
|-------|-----------|----------------|
| Agent | `agent/` | Strands SDK orchestration via BedrockAgentCoreApp, prompt management |
| MCP Server | `mcp_server/` | Tool registration, tenant-scoped data access, context loading |
| Skills | `skills/` | Domain knowledge as plain Markdown (no code) |
| Frontend | `frontend/` | React + Vite + Tailwind + shadcn chat interface with tenant selection, direct SSE streaming to agent |
| Scripts | `scripts/` | Shell-based deployment to AgentCore Runtime |

## Naming Conventions

- Context tools: prefix with `load_*` (e.g., `load_claims_workflow_context`). These read from `skills/*.md`.
- Data tools: prefix with `get_*` (e.g., `get_product_info`). These query `mock_data.py` filtered by tenant ID.
- Skill files: snake_case Markdown in `skills/` (e.g., `claims_workflow.md`).
- Deploy scripts: `deploy_<component>.sh` in `scripts/`.

## Key Rules

- The base prompt (`agent/prompts/system.md`) must stay under 200 tokens and contain no domain-specific content. Domain knowledge is injected at runtime via context tools.
- Tool descriptions in `mcp_server/tools/` drive AgentCore Gateway semantic routing. Keep them descriptive and specific — vague descriptions degrade routing accuracy.
- Multi-tenant isolation: tenants share domain skills but have isolated data. Tenant ID is passed via the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header and must be read from that header in every data tool.
- Mock data in `mcp_server/mock_data.py` is structured as in-memory dicts keyed by tenant ID (e.g., `"axa"`, `"allianz"`).
- Skills are editable without code changes or redeployment. Never embed domain knowledge directly in tool code or the agent prompt.
- No IaC — all deployment is via shell scripts in `scripts/`.
- Gateway → MCP Server auth uses OAuth M2M (client credentials), not IAM. The `deploy_gateway.py` script creates the Cognito resource server, M2M client, and AgentCore credential provider. The `deploy_mcp.sh` script configures the MCP runtime with JWT inbound auth.
- All Python scripts that make AWS API calls include an IPv4 monkey-patch at the top — macOS resolves AWS endpoints to IPv6 but the route is dead, causing hangs. Never remove this patch from `deploy_gateway.py` or `get_token.py`.
- Agent runtime JWT authorizer uses `allowedAudience` when Phase 2 is active (user ID tokens carry `aud` = client ID) or `allowedClients` as Phase 1 fallback (M2M tokens carry `client_id`, no `aud`).
- MCP runtime JWT authorizer always uses `allowedClients` — it only ever receives M2M `client_credentials` tokens from the Gateway.
- Two separate Cognito pools: `sage-tenant-pool` (user ID tokens, Phase 2) and `sage-mcp-pool` (M2M tokens, Gateway→MCP). Never mix them.
