# Implementation Plan: Sage AI Assistant

## Overview

Incremental, feature-sliced build of the Sage AI Assistant. Each task delivers a testable vertical slice — starting with the agent foundation, then validating frontend-to-agent communication early, before layering in context tools, data tools, deployment, and Phase 2 features.

## Tasks

- [x] 1. Agent foundation
  - [x] 1.1 Initialize Python project with `uv`: run `uv init`, create venv with `uv venv`, and add dependencies via `uv add strands-agents bedrock-agentcore fastmcp` and dev deps `uv add --dev hypothesis pytest` (generates `pyproject.toml` and `uv.lock`)
  - [x] 1.2 Create `agent/prompts/system.md` with the reference base prompt from requirements (personality + rules only, ~150 tokens, no domain knowledge)
  - [x] 1.3 Implement `agent/agent.py` — `BedrockAgentCoreApp` entrypoint with Strands SDK `Agent`, `BedrockModel` (Claude Sonnet 4.5), base prompt loading from `agent/prompts/system.md`, and async `invoke()` generator that streams response chunks. The SDK handles `/invocations`, `/ping`, and port 8080 automatically.
  - [x] ~~1.4~~ _(merged into 1.3 — `BedrockAgentCoreApp` eliminates the need for a separate HTTP server file)_
  - [x] 1.5 Verify agent runs locally: `python agent/agent.py` starts, accepts a POST to `/invocations`, and returns a streamed response using only the base prompt
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 11.1, 11.4_

- [x] 2. Custom React frontend with tenant selection (FAST pattern)
  - [x] 2.1 Scaffold React + Vite app in `frontend/` — remove existing CopilotKit/Next.js code, install dependencies (react, react-dom, tailwindcss, shadcn, vite), configure Vite with proxy to `http://localhost:8080` for local dev, set up Tailwind CSS and shadcn
  - [x] 2.2 Create `frontend/src/lib/agentcore-client/` — SSE streaming client adapted from FAST: `types.ts` (StreamEvent, ChunkParser, StreamCallback), `utils/sse.ts` (readSSEStream), `parsers/strands.ts` (parseStrandsChunk), `client.ts` (invokeAgent with tenant header injection)
  - [x] 2.3 Build `frontend/src/components/ChatInterface.tsx` — chat container with message list, input field, streaming state management; calls `invokeAgent()` and accumulates StreamEvents into message segments (interleaved text + tool calls); clears messages/input/streaming state via `useEffect` when `tenantId` changes
  - [x] 2.4 Build `frontend/src/components/ChatMessage.tsx` — renders a single message with markdown formatting and inline tool call components (tool name, streaming input, result)
  - [x] 2.5 Implement `frontend/src/components/TenantSelector.tsx` — shadcn dropdown with AXA and Allianz options, updates parent state on change
  - [x] 2.6 Implement `frontend/src/components/ToolActivity.tsx` — inline tool call display showing tool name, status (running/complete), and result summary
  - [x] 2.7 Build `frontend/src/App.tsx` — root component: TenantSelector + ChatInterface, passes tenantId to AgentCore Client
  - [x] 2.8 Create `frontend/.env.local` with `VITE_AGENT_URL=http://localhost:8080/invocations` for local development
  - [x] 2.9 Update `agent/agent.py` to serialize streaming events as JSON-safe dicts (add `json.dumps(default=str)` for non-serializable Python objects like UUIDs, ModelStopReason tuples)
  - [x] 2.10 Verify end-to-end locally: start agent (`uv run python agent/agent.py`), start frontend (`cd frontend && npm run dev`), send a message via chat UI, confirm streamed response with text and tool activity appears
  - _Requirements: 7.1, 7.2, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 3. Skill files and context tools (local)
  - [x] 3.1 Create `skills/claims_workflow.md` — claims processing domain knowledge covering claim filing, status tracking, approval workflows, documentation requirements
  - [x] 3.2 Create `skills/premium_formulas.md` — premium calculation formulas covering pricing factors, discount rules, rate tables, product-type-specific calculations
  - [x] 3.3 Implement `mcp_server/server.py` — FastMCP entry point (`FastMCP("sage-mcp-server")`) that imports and registers tools from `context_tools.py`
  - [x] 3.4 Implement `mcp_server/tools/context_tools.py` — `load_claims_workflow_context()` and `load_premium_formulas_context()` tools with `@mcp.tool()` decorator, descriptive tool descriptions for semantic routing, file reading from `skills/` directory, and error handling (`FileNotFoundError` → `ToolError` with "missing_skill", `PermissionError` → `ToolError`)
  - [x] 3.5 Wire agent to local MCP server — update `agent/agent.py` to connect to the local FastMCP server for tool discovery (agent can now invoke context tools)
  - [x] 3.6 Verify locally: ask Sage a claims question → agent invokes `load_claims_workflow_context` → skill content appears in response; ask a premium question → `load_premium_formulas_context` invoked
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 5.4, 6.1, 6.4, 6.5, 8.1_

- [ ] 4. Context tools on AWS
  - [x] 4.1 Create `scripts/deploy_mcp.sh` — deploys MCP server to AgentCore runtime using `agentcore launch` with appropriate environment variables
  - [x] 4.2 Create gateway configuration JSON file with `gatewayId: "sage-gateway"`, semantic search config, MCP server target with `metadataConfiguration.allowedRequestHeaders` for tenant header propagation
  - [x] 4.3 Create `scripts/deploy_gateway.sh` — creates/updates AgentCore Gateway from the configuration JSON, sets up Cognito resource server + M2M app client for OAuth client credentials auth, creates AgentCore credential provider (token vault), adds MCP server as gateway target with OAuth credential provider
  - [x] 4.3a Redeploy MCP server with JWT inbound authorization — update `deploy_mcp.sh` to configure the MCP runtime with `authorizer_configuration` pointing to the Cognito User Pool discovery URL and M2M client ID as allowed audience
  - [x] 4.4 Create `scripts/deploy_agent.sh` — deploys Strands agent to AgentCore runtime with `AGENT_PORT=8080` and `AGENT_PATH=/invocations`
  - [x] 4.5 Update `frontend/.env.local` with AgentCore runtime URL and bearer token — use `uv run python scripts/get_token.py` (auto-updates `.env.local` with fresh M2M token)
  - [x] 4.6 Verify on AWS: frontend → agent on AgentCore → MCP server (stdio subprocess) → skill content returned in response with tool activity visible in UI
  - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.2, 6.3, 7.4, 12.Phase1.1, 12.Phase1.2, 12.Phase1.3, 12.Phase1.4, 12.Phase1.5, 12.Phase1.6, 12.Phase1.7_

- [x] 5. Mock data and data tools (local)
  - [x] 5.1 Create `mcp_server/mock_data.py` — `MOCK_DATA` dict keyed by tenant ID (`"axa"`, `"allianz"`) with distinct products (motor insurance with different names, premiums, coverage, discounts) and claims (different claim IDs, statuses, amounts)
  - [x] 5.2 Create shared data models module — `TenantId` enum, `ProductInfo`, `ClaimDetails`, `ToolError` dataclasses as defined in the design document
  - [x] 5.3 Implement `mcp_server/tools/data_tools.py` — `get_product_info(product_type)` and `get_claim_details(claim_reference)` tools with `@mcp.tool()` decorator, descriptive tool descriptions, tenant header extraction via `CurrentHeaders()` from `fastmcp.dependencies` (not `None` default — FastMCP only injects headers when `CurrentHeaders()` is the default value), data filtering by tenant, and error handling (missing header → "invalid_tenant", unknown tenant → "invalid_tenant", claim not found → "not_found")
  - [x] 5.4 Register data tools in `mcp_server/server.py` — import from `data_tools.py` so all 4 tools are exposed
  - [x] 5.5 Update agent to propagate tenant header — ensure `agent/agent.py` reads the tenant header from the incoming request and forwards it on all tool invocation calls through the gateway
  - [x] 5.6 Verify locally: select AXA → ask "What motor products do you offer?" → agent invokes `load_premium_formulas_context` then `get_product_info` → returns AXA motor data; switch to Allianz → same query → returns Allianz motor data; query AXA claim CLM-5454 (Allianz claim) → "not found"
  - _Requirements: 7.5, 7.6, 7.7, 7.8, 7.9, 8.2, 9.1, 9.2, 9.3, 9.4, 9.5, 11.2, 11.3, 11.5_

- [x] 6. Data tools on AWS
  - [x] 6.1 Redeploy MCP server to AgentCore with all 4 tools using `scripts/deploy_mcp.sh` — MCP server runs on port 8000 (not 8080) with `stateless_http=True` in `mcp.run()`
  - [x] 6.2 Verify tenant-scoped data on AWS: select AXA → query product → AXA data; select Allianz → same query → Allianz data
  - [x] 6.3 Verify cross-tenant isolation on AWS: AXA user queries Allianz claim CLM-5454 → "not found"
  - [x] 6.4 Verify all 4 demo scenarios from requirements: AXA premium query, Allianz premium query, AXA claim CLM-12345, Allianz claim CLM-5454
  - _Requirements: 3.3, 4.1, 4.2, 4.3, 4.4, 6.6, 8.3, 8.4, 9.6_

- [ ] 7. Phase 2: JWT authentication
  - [ ] 7.1 Create Cognito User Pool (`sage-tenant-pool`) with 2 app clients: `sage-axa-client` (custom attribute `tenant_id: axa`) and `sage-allianz-client` (custom attribute `tenant_id: allianz`), token claims include `custom:tenant_id`
  - [ ] 7.2 Configure AgentCore Identity with credential provider for JWT validation from the Cognito User Pool
  - [ ] 7.3 Update `agent/agent.py` to extract `tenant_id` from JWT `custom:tenant_id` claim when present, and set it as the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header for gateway propagation (fallback to direct header for Phase 1 compatibility)
  - [ ] 7.4 Update React frontend to authenticate against tenant-specific Cognito app client, obtain JWT, and send via `Authorization` header in the AgentCore Client's POST to `/invocations`
  - [ ] 7.5 Verify: login as AXA user → JWT contains `custom:tenant_id: axa` → agent extracts tenant from JWT → data tools return AXA data; same for Allianz
  - _Requirements: 12.Phase2.1, 12.Phase2.2, 12.Phase2.3, 12.Phase2.4_

- [ ] 8. Phase 2: Bedrock Guardrails
  - [ ] 8.1 Create Bedrock Guardrail (`sage-domain-guardrail`) with topic policy denying out-of-domain questions (weather, jokes, stock prices, etc.) with example prompts
  - [ ] 8.2 Integrate guardrail identifier into Strands SDK agent configuration in `agent/agent.py`
  - [ ] 8.3 Verify: ask "What's the weather today?" → guardrail blocks with managed response; ask "How is premium calculated?" → passes through to normal flow
  - _Requirements: 12.Phase2.5_

- [ ] 9. Property-based and unit tests
  - [ ] 9.1 Backend property test: Property 1 (Skill Content Round-Trip) — write random Markdown to skill file, invoke context tool, assert output matches file content. Tag: `Feature: sage-ai-assistant, Property 1: Skill Content Round-Trip`
  - [ ] 9.2 Backend property test: Property 2 (MCP Server Tool Invocation Correctness) — generate valid tool names and parameters, invoke on MCP server, assert non-error response with correct schema. Tag: `Feature: sage-ai-assistant, Property 2: MCP Server Tool Invocation Correctness`
  - [ ] 9.3 Backend property test: Property 3 (MCP Server Error Response Structure) — generate failure scenarios, invoke tools, assert error contains tool name and reason. Tag: `Feature: sage-ai-assistant, Property 3: MCP Server Error Response Structure`
  - [ ] 9.4 Frontend property test: Property 4 (Tenant Header Propagation) — generate tenant selections, assert every POST request from AgentCore Client includes correct header. Tag: `Feature: sage-ai-assistant, Property 4: Tenant Header Propagation from Frontend`
  - [ ] 9.5 Backend property test: Property 5 (Agent Tenant Header Extraction) — generate valid tenant IDs in request headers, assert agent extracts correct value. Tag: `Feature: sage-ai-assistant, Property 5: Agent Tenant Header Extraction`
  - [ ] 9.6 Backend property test: Property 6 (Data Tool Tenant Isolation) — generate tenant ID + data query combos, assert all results belong to queried tenant. Tag: `Feature: sage-ai-assistant, Property 6: Data Tool Tenant Isolation`
  - [ ] 9.7 Backend property test: Property 7 (Cross-Tenant Data Rejection) — generate claim refs belonging to tenant A, invoke with tenant B, assert "not found". Tag: `Feature: sage-ai-assistant, Property 7: Cross-Tenant Data Rejection`
  - [ ] 9.8 Backend property test: Property 8 (Skill Tenant Independence) — generate pairs of tenant IDs, invoke same context tool, assert identical output. Tag: `Feature: sage-ai-assistant, Property 8: Skill Tenant Independence`
  - [ ] 9.9 Backend property test: Property 9 (Agent Streaming Response) — generate valid chat requests, assert response is async iterable of valid chunks. Tag: `Feature: sage-ai-assistant, Property 9: Agent Streaming Response`
  - [ ] 9.10 Backend property test: Property 10 (JWT Tenant Claim Extraction) — generate JWT tokens with random tenant claims, assert extracted tenant matches claim. Tag: `Feature: sage-ai-assistant, Property 10: JWT Tenant Claim Extraction`
  - [ ] 9.11 Backend unit tests: base prompt validation (matches reference, ≤200 tokens, no domain keywords), mock data structure (AXA/Allianz distinct), tool registration (all 4 tools registered), skill file missing error, gateway config validation
  - [ ] 9.12 Frontend unit tests: tenant selector renders AXA/Allianz options, AgentCore Client `invokeAgent()` includes tenant header on POST, Strands parser correctly handles text/tool_use/tool_result/result events, SSE reader splits lines correctly, tool activity displays inline, loading state during streaming
  - _Requirements: All — cross-cutting validation_
