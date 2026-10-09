---
inclusion: always
---

# Product: Sage AI Assistant

Sage is a two-tenant insurance assistant. It combines a minimal base prompt, Agent Skills loaded from AgentCore Registry, tenant-scoped MCP data tools, and a shared API that owns authorization and isolation.

## Core principles

- Domain knowledge lives in `skills/*/SKILL.md`, not in the base prompt or data tools.
- The Strands `AgentSkills` plugin loads approved skills from AgentCore Registry on demand.
- MCP tools describe and request business data; they never access the datastore directly.
- Tenant_A and Tenant_B are security identifiers. AXA and Allianz are display names only.
- Every hop receives its own user access token, issued by the lane's Auth0 tenant for that receiver only. Workloads obtain the next hop's token by on-behalf-of (OBO) token exchange through AgentCore Identity. No component forwards the token it received.
- Users sign in once through the lane's Auth0 tenant, which signs them in through the lane's Cognito pool and its existing customer IdP federation. No consent or approval screen appears after sign-in.
- AgentCore managed authorizers validate each tenant lane before application code runs.
- The shared Sage API independently validates both issuers and remains the final business-authorization and tenant-isolation boundary.

## Current demo

| Category | Capability |
|---|---|
| Skill | `claims-workflow` |
| Skill | `premium-formulas` |
| Data tool | `get_product_info` |
| Data tool | `get_claim_details` |

Data tools call the shared Sage API with a token exchanged for the Sage API. Demo data lives in `sage_api/mock_data.py`, keyed only by Tenant_A and Tenant_B.

## Behavioral constraints

- Never return cross-tenant data.
- Never treat a prompt, payload value, query parameter, model output, or caller tenant header as identity authority.
- Never forward a received bearer to another service. The MCP authorization specification forbids token passthrough.
- Never expose access tokens, refresh tokens, client secrets or renewal material to model input, tool results, logs, errors, or UI content.
- Clear the conversation when lane, subject, or tenant identity changes; reject late events from the old session.
- Keep renewal material in browser communication with the selected lane's Auth0 tenant.
- Do not add M2M, static-token, shared service-token, or context-token paths. Machine-to-machine tokens never reach a Sage door.

## Transition from JWT passthrough

The previous design forwarded the original Cognito access token through every hop (Route C). It stays deployed, and its code stays in the repository, until the `downstream-user-grants` spec reaches cutover and retirement. New work follows the OBO model above. Do not extend Route C code paths.

## Adding capabilities

1. For domain knowledge, add `skills/<topic>/SKILL.md` with accurate frontmatter and instructions.
2. For tenant-scoped data, add the API-owned data/operation under `sage_api/`, then register a small MCP tool that calls it.
3. Keep authorization and isolation in the Sage API; MCP tools only exchange for the Sage API token and pass safe operation inputs.
