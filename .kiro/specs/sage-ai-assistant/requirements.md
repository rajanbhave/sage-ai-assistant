# Requirements Document

## Introduction

Sage AI Assistant is a domain-aware conversational agent built on a minimal base prompt architecture with AgentCore Gateway semantic routing. Instead of a monolithic system prompt packed with hardcoded tool sequences and defensive guardrails, Sage uses a compact base prompt (~150 tokens covering personality and rules) combined with an AgentCore Gateway that performs semantic search over registered tools at runtime. When a user query arrives, the gateway matches it against tool descriptions and injects only the relevant domain-specific skill context. This yields focused context windows, fewer tool calls, and accurate responses without context bloat.

The system comprises three layers: (1) context tools that load domain knowledge from Markdown skills, (2) data tools that retrieve specifics from backend systems, and (3) the AgentCore Gateway that semantically routes queries to the right tools. The architecture is designed for multi-tenant isolation and is hosted as an MCP server on AgentCore runtime.

### Demo Scope

This is an end-to-end demo showcasing the full flow from UI to AgentCore modules for two tenants: **AXA** and **Allianz**.

- **Frontend**: React chat interface — login screen (Phase 2, active) or tenant selector dropdown (Phase 1 fallback).
- **Agent SDK**: Strands SDK for building the Sage agent with tool use capabilities.
- **Foundation Model**: Claude Sonnet 4.5 via Amazon Bedrock.
- **Context Modules (shared across tenants)**: 2 context tools deployed in the MCP server that load skill Markdown as additional prompt context (similar to Claude Code skills). The AgentCore Gateway semantically routes queries to these tools:
  1. `load_claims_workflow_context` — Claims processing domain knowledge
  2. `load_premium_formulas_context` — Premium calculation formulas and rules
- **Data Tools (tenant-scoped)**: 2 data tools deployed in the same MCP server with mock data for AXA and Allianz:
  1. `get_product_info` — Returns tenant-specific product/policy details
  2. `get_claim_details` — Returns tenant-specific claim information
- **MCP Server Framework**: FastMCP (Python) for defining the MCP server with decorator-based tool registration.
- **Gateway as Classifier Replacement**: The AgentCore Gateway's semantic search replaces the customer's existing classifier model for skill selection. Instead of a separate model analyzing the query, the gateway matches queries to tool descriptions at runtime.
- **Tenant ID Propagation**: Tenant identity flows via `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` custom header through the full request path:
  ```
  React (sets header) → AgentCore Runtime → Strands Agent (reads header)
    → AgentCore Gateway (semantic routing + header propagation via metadataConfiguration)
      → MCP Server / FastMCP → Data tools filter by tenant ID
  ```
- **Runtime**: AgentCore Gateway for semantic routing, MCP server hosting on AgentCore runtime.
- **Deployment**: Local-first (Python process + frontend dev server), then deploy to AWS via scripts/CLI (no IaC).

### Demo Scenarios

| Tenant | User Query | Expected Flow |
|--------|-----------|---------------|
| AXA | "How is the premium calculated for a motor policy?" | → `load_premium_formulas_context` (appends domain context) → `get_product_info` (returns AXA motor product details) |
| Allianz | "How is the premium calculated for a motor policy?" | → `load_premium_formulas_context` (appends domain context) → `get_product_info` (returns Allianz motor product details) |
| AXA | "What's the status of claim CLM-12345?" | → `load_claims_workflow_context` (appends domain context) → `get_claim_details` (returns AXA claim CLM-12345) |
| Allianz | "What's the status of claim CLM-5454?" | → `load_claims_workflow_context` (appends domain context) → `get_claim_details` (returns Allianz claim CLM-5454) |
| AXA | "What motor products do you offer and how is the premium worked out?" | → `load_premium_formulas_context` (appends premium calculation rules) → `get_product_info` (returns AXA Drive Protect details with base premium) |
| Allianz | "Walk me through how my claim CLM-5454 is being processed" | → `load_claims_workflow_context` (appends claims workflow domain knowledge) → `get_claim_details` (returns Allianz CLM-5454 status and details) |

## Glossary

- **Sage_Agent**: The conversational AI agent that processes user queries using a minimal base prompt and dynamically loaded domain context.
- **Base_Prompt**: The minimal system prompt (not exceeding 200 tokens) that defines Sage's personality and behavioral rules without any domain-specific knowledge.
- **AgentCore_Gateway**: The runtime routing component that performs semantic search (`x_amz_bedrock_agentcore_search`) over all registered tools to match user queries to relevant context and data tools.
- **Context_Tool**: A tool prefixed with `load_*` that loads domain-specific instructions from a corresponding Markdown skill file. The demo includes two context tools: `load_claims_workflow_context` and `load_premium_formulas_context`.
- **Data_Tool**: A tool that retrieves tenant-scoped data from backend systems. The demo includes two data tools: `get_product_info` and `get_claim_details`, backed by mock data for AXA and Allianz tenants.
- **Skill**: A Markdown file stored in the `skills/` directory containing domain knowledge for a specific feature area (e.g., premium formulas, claims workflow).
- **Semantic_Search**: The gateway's mechanism for matching a user query against tool descriptions to determine which tools to invoke.
- **MCP_Server**: The Model Context Protocol server built with FastMCP (Python) that hosts all tools on AgentCore runtime and exposes them to the gateway.
- **FastMCP**: The Python framework used to define the MCP server with decorator-based tool registration.
- **Tenant**: An isolated customer data environment. Tenants share common Skills (domain knowledge) but have isolated data access boundaries. Tenant identity is propagated via the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` custom header.
- **Tool_Description**: The natural-language description registered with each tool that the gateway uses for semantic matching.

## Requirements

### Requirement 1: Minimal Base Prompt

**User Story:** As a system architect, I want the base system prompt to contain only personality and behavioral rules, so that all domain knowledge is loaded dynamically through context tools and the prompt stays within token budget.

#### Reference Base Prompt

The following is the canonical base prompt for the Sage_Agent. It SHALL be used as-is or as the reference baseline:

```
You are Sage, the AI assistant for the Insurance Suite.

For domain questions (claims, premiums, products, workflows):
1. ALWAYS load the relevant context tool first (load_claims_workflow_context, load_premium_formulas_context)
2. Then use data tools (get_claim_details, get_product_info) if the user asks for specific information

For responses:
- Do NOT mention or describe the tools you are using. Simply provide the answer directly.
- Never guess policy numbers, amounts, or dates. Always retrieve them from data tools.
- Always respond in English unless the user writes in another language.
- Be concise and precise.
```

#### Acceptance Criteria

1. THE Base_Prompt SHALL contain only Sage_Agent personality traits and behavioral rules as defined in the Reference Base Prompt above.
2. THE Base_Prompt SHALL not exceed 200 tokens in length.
3. THE Base_Prompt SHALL not contain any domain-specific knowledge, tool invocation sequences, or hardcoded guardrails.
4. WHEN the Sage_Agent is initialized, THE Base_Prompt SHALL be loaded from `agent/prompts/` as the sole static system prompt.
5. THE Base_Prompt SHALL instruct the Sage_Agent to search the AgentCore_Gateway for relevant Context_Tools before using Data_Tools.

### Requirement 2: Skill Content Separation

**User Story:** As a developer, I want domain knowledge stored in separate Markdown files in the `skills/` directory, so that I can update domain content without modifying tool registration code.

#### Acceptance Criteria

1. THE Sage_Agent SHALL store each domain knowledge area as a separate Markdown file in the `skills/` directory.
2. WHEN a Context_Tool is invoked, THE Context_Tool SHALL load its content exclusively from the corresponding Markdown Skill file.
3. THE Sage_Agent SHALL support a minimum of two Skill files for the demo: `claims_workflow.md` and `premium_formulas.md`, one for each Context_Tool.
4. WHEN a Skill file is updated, THE Context_Tool SHALL serve the updated content on the next invocation without requiring tool code changes or redeployment of tool registration logic.
5. IF a Skill file is missing or unreadable, THEN THE Context_Tool SHALL return a descriptive error message indicating the missing Skill file path.

### Requirement 3: AgentCore Gateway Semantic Routing

**User Story:** As a system architect, I want the AgentCore Gateway to semantically match user queries to registered tools at runtime, so that the agent receives only the domain context it needs without hardcoded routing logic.

#### Acceptance Criteria

1. WHEN a user message is received, THE AgentCore_Gateway SHALL perform a Semantic_Search (`x_amz_bedrock_agentcore_search`) over all registered Context_Tools and Data_Tools.
2. WHEN the Semantic_Search matches a Context_Tool, THE AgentCore_Gateway SHALL return the matched Context_Tool identifier to the Sage_Agent for invocation.
3. WHEN the Semantic_Search matches a Data_Tool, THE AgentCore_Gateway SHALL return the matched Data_Tool identifier to the Sage_Agent for invocation.
4. THE AgentCore_Gateway SHALL select tools based solely on Tool_Description quality and user query semantics, without relying on hardcoded routing rules in the Base_Prompt.
5. WHEN no tools match the user query with sufficient confidence, THE AgentCore_Gateway SHALL return an empty tool set, allowing the Sage_Agent to respond using only the Base_Prompt.

### Requirement 4: Context Tool Invocation Flow

**User Story:** As a user, I want Sage to first load the relevant domain skill before retrieving specific data, so that responses are grounded in domain knowledge and are accurate.

#### Acceptance Criteria

1. WHEN the AgentCore_Gateway returns both a Context_Tool and a Data_Tool match, THE Sage_Agent SHALL invoke the Context_Tool before invoking the Data_Tool.
2. WHEN a Context_Tool is invoked, THE Sage_Agent SHALL use the loaded Skill content as additional context for processing the user query.
3. WHEN only a Data_Tool match is returned, THE Sage_Agent SHALL invoke the Data_Tool directly without requiring a preceding Context_Tool invocation.
4. WHEN only a Context_Tool match is returned, THE Sage_Agent SHALL respond using the loaded Skill content without invoking any Data_Tool.

### Requirement 5: Tool Registration and Extensibility

**User Story:** As a developer, I want to add new skills by registering a new tool with a descriptive name, so that the gateway automatically routes relevant queries to the new skill without prompt engineering.

#### Acceptance Criteria

1. WHEN a new Context_Tool is registered with the AgentCore_Gateway, THE AgentCore_Gateway SHALL include the new Context_Tool in subsequent Semantic_Search operations.
2. THE AgentCore_Gateway SHALL route queries to the newly registered Context_Tool based on its Tool_Description without requiring changes to the Base_Prompt or existing tool code.
3. THE Sage_Agent SHALL support registration of new Data_Tools following the same pattern as Context_Tools.
4. WHEN a Context_Tool is removed from the registry, THE AgentCore_Gateway SHALL exclude the removed Context_Tool from subsequent Semantic_Search operations.

### Requirement 6: MCP Server Hosting on AgentCore Runtime

**User Story:** As a platform engineer, I want all tools (context and data) hosted as a single MCP server on AgentCore runtime, so that the gateway has full visibility for semantic routing and the setup is simple.

#### Acceptance Criteria

1. THE MCP_Server SHALL be built using FastMCP (Python) with decorator-based tool registration.
2. THE MCP_Server SHALL host all Context_Tools and Data_Tools together on AgentCore runtime as a single server.
3. THE MCP_Server SHALL expose all registered tools to the AgentCore_Gateway via the Model Context Protocol, enabling the gateway's semantic search to route across both Context_Tools and Data_Tools.
4. WHEN the MCP_Server receives a tool invocation request, THE MCP_Server SHALL execute the corresponding tool and return the result to the Sage_Agent.
5. IF the MCP_Server encounters a tool execution failure, THEN THE MCP_Server SHALL return a structured error response including the tool name and failure reason.
6. THE MCP_Server SHALL support concurrent tool invocation requests from multiple Sage_Agent sessions.

### Requirement 7: Multi-Tenant Isolation

**User Story:** As a platform engineer, I want each customer tenant to have isolated data access while sharing common domain skills, so that the same Sage agent serves multiple tenants with tenant-specific data.

#### Demo Tenants

The demo showcases two tenants with mock data:
- **AXA**: Motor products, claims (e.g., CLM-12345)
- **Allianz**: Motor products, claims (e.g., CLM-5454)

#### Acceptance Criteria

1. THE React frontend SHALL provide a login screen (Phase 2) or tenant selector dropdown (Phase 1 fallback) allowing the user to establish their tenant identity (AXA or Allianz) at session start.
2. THE React frontend SHALL send the selected tenant identifier as the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` HTTP header with each request.
3. THE Sage_Agent SHALL read the tenant identifier from the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` request header and associate the session with that Tenant.
4. THE AgentCore_Gateway target SHALL be configured with `metadataConfiguration.allowedRequestHeaders` to propagate the tenant header to the MCP_Server.
5. WHEN a Data_Tool is invoked, THE Data_Tool SHALL read the tenant identifier from the propagated header and filter results to return only data belonging to that Tenant.
6. THE Skill files SHALL be shared across all Tenants (skills contain domain knowledge, not tenant-specific data).
7. WHEN an AXA user queries claim details, THE `get_claim_details` tool SHALL return only AXA claim data.
8. WHEN an Allianz user queries claim details, THE `get_claim_details` tool SHALL return only Allianz claim data.
9. THE mock data SHALL include distinct product configurations and claim records for each Tenant to visually demonstrate isolation during the demo.

### Requirement 8: Tool Description Quality for Routing Accuracy

**User Story:** As a developer, I want tool descriptions to be the sole driver of routing accuracy, so that the gateway can reliably match user queries to the correct tools.

#### Acceptance Criteria

1. THE Tool_Description for each Context_Tool SHALL clearly describe the domain area, key topics, and query types the tool handles.
2. THE Tool_Description for each Data_Tool SHALL clearly describe the data source, retrieval capability, and expected query patterns.
3. WHEN two or more Tool_Descriptions cover overlapping domains, THE AgentCore_Gateway SHALL select the most specific matching tool based on query-to-description similarity.
4. THE Sage_Agent SHALL not load Skills that are not matched by the AgentCore_Gateway Semantic_Search for the current query (no context bloat).

### Requirement 9: Data Tools with Mock Data

**User Story:** As a demo viewer, I want Sage to retrieve tenant-specific product and claim data, so that I can see multi-tenant isolation in action with realistic responses.

#### Acceptance Criteria

1. THE Sage_Agent SHALL support two Data_Tools: `get_product_info` and `get_claim_details`.
2. THE `get_product_info` tool SHALL accept a product type parameter and read the tenant identifier from the propagated request header, returning tenant-specific product configuration from mock data.
3. THE `get_claim_details` tool SHALL accept a claim reference parameter and read the tenant identifier from the propagated request header, returning tenant-specific claim details from mock data.
4. THE mock data SHALL include distinct records for AXA and Allianz tenants (different product configurations, different claim numbers and statuses).
5. IF a Data_Tool is invoked with a claim reference that does not belong to the associated Tenant, THEN THE Data_Tool SHALL return a "not found" response.
6. WHEN a Data_Tool returns results, THE Sage_Agent SHALL incorporate the returned data into the response to the user.

### Requirement 10: React Chat Frontend

**User Story:** As a demo viewer, I want to interact with Sage through a modern chat interface with tenant selection, so that I can see the end-to-end flow and multi-tenant isolation from user input to agent response.

#### Acceptance Criteria

1. THE demo SHALL provide a chat frontend built with React + Vite + Tailwind CSS + shadcn/ui.
2. THE React frontend SHALL include a tenant selector dropdown with options for AXA and Allianz.
3. THE React frontend SHALL pass the selected tenant identifier as the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` HTTP header with each request (Phase 1), or include it in the JWT token claims (Phase 2).
4. THE React frontend SHALL send user messages to the Sage_Agent backend and display streamed responses.
5. THE React frontend SHALL visually indicate when the Sage_Agent is processing a query (loading state).
6. THE React frontend SHALL display tool invocation activity so demo viewers can observe the gateway routing, context loading, and tenant-scoped data retrieval in action.

### Requirement 11: Strands SDK Agent Implementation

**User Story:** As a developer, I want the Sage agent built with Strands SDK, so that it integrates natively with AgentCore runtime and supports tool use capabilities.

#### Acceptance Criteria

1. THE Sage_Agent SHALL be implemented using the Strands SDK.
2. THE Sage_Agent SHALL discover and consume Context_Tools and Data_Tools from the MCP_Server via the AgentCore_Gateway's semantic search.
3. THE Strands SDK agent SHALL connect to the AgentCore_Gateway for semantic tool routing via `x_amz_bedrock_agentcore_search`.
4. THE Strands SDK agent SHALL support streaming responses to the React frontend.
5. THE Strands SDK agent SHALL read the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header from the incoming request context and make it available for Data_Tool invocations.

### Requirement 12: Authentication and Authorization

**User Story:** As a platform engineer, I want the demo to showcase both IAM authentication and JWT-based tenant authentication, so that the customer sees the progression from simple setup to production-ready tenant identity.

#### Phase 1: OAuth M2M Authentication (Gateway → MCP)

1. THE AgentCore Runtime (agent) inbound auth SHALL use JWT authorization with `allowedClients` for Phase 1 (M2M `client_credentials` tokens from the M2M Cognito pool carry `client_id` but no `aud` claim).
2. THE AgentCore Gateway inbound auth SHALL use IAM (SigV4) for agent-to-gateway calls.
3. THE AgentCore Runtime IAM role SHALL include `bedrock-agentcore:InvokeGateway` permission for the gateway.
4. THE Gateway outbound auth to MCP_Server targets SHALL use OAuth with client credentials grant (M2M). Note: AgentCore Gateway does not support IAM/SigV4 for MCP server targets — only OAuth is supported.
5. THE MCP_Server runtime SHALL be configured with JWT inbound authorization using `allowedClients`, accepting tokens issued by the M2M Cognito User Pool (`sage-mcp-pool`). `allowedClients` is required (not `allowedAudience`) because M2M `client_credentials` tokens carry `client_id` but no `aud` claim.
6. A Cognito resource server and M2M app client (client credentials grant) SHALL be created for the Gateway-to-MCP authentication flow.
7. An AgentCore credential provider (token vault entry) SHALL be created to store the M2M client credentials for the Gateway.
8. THE tenant identifier SHALL be passed via the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` custom header from the React frontend.

#### Phase 2: JWT Tenant Authentication (Active)

1. THE AgentCore Runtime (agent) inbound auth SHALL accept Cognito ID tokens from the tenant user pool (`sage-tenant-pool`). The JWT authorizer SHALL use `allowedAudience` with the AXA and Allianz app client IDs — ID tokens carry `aud` = client ID.
2. THE React frontend SHALL authenticate users against the tenant-specific Cognito app client (`sage-tenant-a-client` or `sage-tenant-b-client`) using `USER_PASSWORD_AUTH` via `amazon-cognito-identity-js`, obtain an ID token containing `custom:tenant_id`, and send it via the `Authorization: Bearer` header on every `/invocations` request.
3. THE Sage_Agent SHALL extract the tenant identifier from the JWT `custom:tenant_id` claim (base64-decoded payload, no signature verification needed — runtime already validated) and set it as the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id` header for gateway propagation. Phase 1 direct-header fallback is retained for compatibility.
4. THE tenant user pool SHALL be deployed via `scripts/deploy_user_pool.py`, which creates the pool, two app clients (one per tenant), and demo users (`axa-user`, `allianz-user`) with permanent passwords and `custom:tenant_id` attributes.
5. THE Sage_Agent SHALL integrate Amazon Bedrock Guardrails for out-of-domain query handling, replacing the base prompt's static instruction with a managed guardrail policy.
