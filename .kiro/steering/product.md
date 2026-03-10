---
inclusion: always
---

# Product: Sage AI Assistant

Sage is a multi-tenant, domain-aware conversational AI agent for the Insurance Suite. It combines a minimal base prompt with dynamic context injection — an AgentCore Gateway semantically routes user queries to the right tools at runtime, so the agent never needs hardcoded routing logic.

## Core Design Principles

- Separation of knowledge and logic: domain knowledge lives in `skills/*.md` files, never in tool code or the agent prompt.
- Semantic routing over explicit routing: tool descriptions are the routing mechanism. Write them to be descriptive and specific — vague descriptions degrade Gateway accuracy.
- Minimal base prompt: the system prompt (`agent/prompts/system.md`) defines personality and behavioral rules only (~150 tokens, max 200). All domain content is injected at runtime via context tools.
- Tenant isolation by convention: tenants share domain skills but have fully isolated data. The tenant ID header (`X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id`) must be respected in every data tool.

## Tool Taxonomy

There are exactly two categories of tools. Every new tool must fit one:

| Category | Prefix | Purpose | Data source |
|----------|--------|---------|-------------|
| Context tools | `load_*` | Inject domain knowledge into the conversation | `skills/*.md` |
| Data tools | `get_*` | Return tenant-scoped business data | `mcp_server/mock_data.py` |

Context tools are stateless readers of Markdown skill files. Data tools filter in-memory mock data by tenant ID.

## Adding New Capabilities

When adding a new tool or domain area:

1. If it's domain knowledge (workflows, formulas, rules) — create a new `skills/<topic>.md` file and a corresponding `load_<topic>_context` tool in `context_tools.py`.
2. If it's tenant-scoped data — add the data structure to `mock_data.py` keyed by tenant ID, then create a `get_<entity>` tool in `data_tools.py`.
3. Write tool descriptions that clearly express what the tool returns and when it should be used — the Gateway relies on these for routing.
4. Never mix context loading and data retrieval in a single tool.

## Current Demo Scope

Two tenants: AXA and Allianz, with in-memory mock data. Four registered tools:

- `load_claims_workflow_context` — claims processing domain knowledge
- `load_premium_formulas_context` — premium calculation rules
- `get_product_info` — tenant-scoped product details
- `get_claim_details` — tenant-scoped claim information

## Behavioral Constraints

- The agent must not hallucinate domain facts. If the relevant skill file hasn't been loaded into context, the agent should call the appropriate `load_*` tool before answering domain questions.
- Data responses must always be scoped to the current tenant. Never return cross-tenant data.
- The frontend passes the tenant ID via the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header. Backend tools must read from this header, not from user input.
- The agent must never mention tool names or internal tool calls in its responses. Tool activity is visible in the UI for demo purposes, but the agent's text should read naturally.
- When the tenant changes in the frontend, the conversation must be cleared to prevent cross-tenant context leakage.

## Gateway & Runtime Authentication

- AgentCore Gateway → MCP Runtime: OAuth M2M (`client_credentials` grant) via Cognito resource server. The MCP runtime uses `customJWTAuthorizer` with `allowedClients` (not `allowedAudience`) because Cognito M2M tokens carry `client_id` but no `aud` claim.
- Frontend → Agent Runtime: same Cognito M2M token obtained via `scripts/get_token.py`. The agent runtime also uses `allowedClients` for the same reason.
- `deploy_gateway.py` handles Cognito pool, domain, resource server, M2M client, credential provider, gateway, and target creation. `deploy_mcp.sh` and `deploy_agent.sh` configure JWT inbound auth on their respective runtimes.
- To refresh the bearer token: `uv run python scripts/get_token.py` — auto-updates `frontend/.env.local`.
