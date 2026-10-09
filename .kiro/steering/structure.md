---
inclusion: always
---

# Project Structure

```text
sage-ai-assistant/
├── agent/
│   ├── agent.py                    # Agent Runtime entrypoint, OBO exchange for the Gateway token
│   └── prompts/system.md           # Minimal base prompt
├── auth0/
│   ├── actions/post_login.js       # Sets custom:tenant_id and cognito_sub on every token
│   └── tenant.template.json        # Per-lane Auth0 tenant configuration as data
├── frontend/
│   └── src/                        # Lane-bound browser auth (Auth0) and chat UI
├── mcp_server/
│   ├── server.py                   # FastMCP entrypoint
│   ├── identity.py                 # Managed-validated subject/tenant extraction
│   ├── sage_api_client.py          # Calls the shared API with the exchanged API token
│   └── tools/data_tools.py         # MCP tool registration only
├── sage_api/
│   ├── identity.py                 # Independent two-issuer JWT validation
│   ├── http.py                     # Authorization and tenant data boundary
│   └── mock_data.py                # Tenant_A/Tenant_B demo records
├── sage_identity/
│   ├── models.py                   # Immutable lane and issuer records
│   ├── managed_authorizers.py      # AgentCore JWT authorizer payloads
│   ├── downstream.py               # OBO exchange and same-principal checks
│   ├── transport.py                # Credential-safe transport and errors
│   ├── cognito.py                  # Cognito token customization (upstream of Auth0)
│   └── deployment_evidence.py      # Deployment proof evaluation
├── scripts/
│   ├── render_identity_deployments.py
│   ├── plan_identity_deployment.py
│   └── deploy_*.py / deploy_*.sh
├── skills/<name>/SKILL.md
└── tests/
```

`auth0/` and `sage_identity/downstream.py` are added by the `downstream-user-grants` spec. Until its retirement phase, Route C files still describe exact bearer forwarding.

## Ownership

| Layer | Directory | Responsibility |
|---|---|---|
| Browser | `frontend/` | Trusted lane selection, Auth0 session, browser-only renewal |
| Identity issuer | `auth0/` | Per-lane Auth0 tenant configuration and the tenant-claim Action |
| Agent | `agent/` | Model orchestration, Registry skills, OBO exchange for the Gateway |
| MCP | `mcp_server/` | Tool registration, hosting-lane identity binding, OBO exchange for the Sage API |
| Shared API | `sage_api/` | Independent JWT validation, business authorization, tenant isolation |
| Shared identity | `sage_identity/` | Identity models, exchange helpers, transport, managed authorizer rendering |
| Deployment | `scripts/` | Two-lane rendering, dry run, and explicitly invoked AWS and Auth0 deployment |

## Naming rules

- Architecture route and option labels (Route A/B/C, Option A/B1/B2) are explanation terms only. Do not encode them in package names, identifiers, environment variables, log fields, config keys, or test filenames. Standard protocol terms such as `obo` and `token_exchange` are allowed.
- Internal tenant identifiers remain exactly `Tenant_A` and `Tenant_B`; AXA and Allianz are display-only names.
- Deploy scripts are named `deploy_<component>.*`; identity render/planning helpers use responsibility-based names.
- Skills live in `skills/<name>/SKILL.md`; data tools use `get_*` names.

## Security rules

- Every hop receives a token whose `aud` names that receiver. No component forwards a received bearer.
- Agent and MCP obtain downstream tokens only through AgentCore Identity OBO exchange, using the provider, scope and audience from trusted deployment configuration.
- Before using an exchanged token, the workload checks that issuer, subject, tenant and `cognito_sub` match the inbound principal and that `aud` is the intended receiver.
- Each lane trusts only its own Auth0 tenant. Auth0 tenants, connections, clients and credential providers are lane-specific.
- AgentCore managed authorizers own signature, expiry, issuer, audience, client, local scope, and exact lane tenant-claim validation.
- Agent and MCP application code must not claim to re-verify managed authentication decisions.
- Sage API independently verifies the token because it accepts both trusted issuers and owns the data boundary. It also checks `typ`, the calling client and the `act` delegation chain.
- Tenant authority never comes from prompts, model output, query parameters, caller tenant headers or Auth0 `user_metadata`. Only the Auth0 Action sets the tenant claim, from the verified Cognito value.
- Browser renewal material never leaves the browser.
- No M2M, static-token, shared service-token or context-token path belongs in this repository. OBO clients authenticate to Auth0 with `PRIVATE_KEY_JWT`, and their KMS private keys are usable only through AgentCore Identity. Any fallback client secret lives only in Auth0 and AgentCore Identity.

## Deployment rules

- Deployment configuration defaults to `scripts/identity_deployment.json` and may be overridden with `SAGE_IDENTITY_CONFIG_FILE`.
- Renderers and the deployment planner are local and mutation-free.
- AWS and Auth0 mutation occurs only through an explicitly invoked deploy command with `--confirm`, after configuration, rollback, and security approval.
- Changes to resources shared with Route C (Cognito pools, domains, pre-token Lambdas) follow the spec's shared-resource table: snapshot, Route C regression check before and after, rollback on failure.
- Auth0 management credentials are read at run time and held in memory only.
- Preserve the IPv4 endpoint workaround in AWS deployment scripts until the macOS networking constraint is removed and verified.
