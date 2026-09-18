---
inclusion: always
---

# Project Structure

```text
sage-ai-assistant/
├── agent/
│   ├── agent.py                    # Agent Runtime entrypoint and exact bearer forwarding
│   └── prompts/system.md           # Minimal base prompt
├── frontend/
│   └── src/                        # Lane-bound browser auth and chat UI
├── mcp_server/
│   ├── server.py                   # FastMCP entrypoint
│   ├── identity.py                 # Managed-validated subject/tenant extraction
│   ├── sage_api_client.py          # Exact bearer forwarding to shared API
│   └── tools/data_tools.py         # MCP tool registration only
├── sage_api/
│   ├── identity.py                 # Independent two-issuer JWT validation
│   ├── http.py                     # Authorization and tenant data boundary
│   └── mock_data.py                # Tenant_A/Tenant_B demo records
├── sage_identity/
│   ├── models.py                   # Immutable lane and issuer records
│   ├── managed_authorizers.py      # AgentCore JWT authorizer payloads
│   ├── transport.py                # Credential-safe transport and errors
│   ├── cognito.py                  # Access-token customization
│   └── deployment_evidence.py      # Target/source proof evaluation
├── scripts/
│   ├── render_identity_deployments.py
│   ├── plan_identity_deployment.py
│   └── deploy_*.py / deploy_*.sh
├── skills/<name>/SKILL.md
└── tests/
```

## Ownership

| Layer | Directory | Responsibility |
|---|---|---|
| Browser | `frontend/` | Trusted lane selection, Cognito access-token session, browser-only renewal |
| Agent | `agent/` | Model orchestration, Registry skills, exact bearer forwarding |
| MCP | `mcp_server/` | Tool registration, hosting-lane identity binding, Sage API calls |
| Shared API | `sage_api/` | Independent JWT validation, business authorization, tenant isolation |
| Shared identity | `sage_identity/` | Reusable identity models and transport, managed authorizer rendering |
| Deployment | `scripts/` | Two-lane rendering, dry run, and explicitly invoked AWS deployment |

## Naming rules

- Architecture route names are explanation terms only. Do not encode them in package names, identifiers, environment variables, log fields, config keys, or test filenames.
- Internal tenant identifiers remain exactly `Tenant_A` and `Tenant_B`; AXA and Allianz are display-only names.
- Deploy scripts are named `deploy_<component>.*`; identity render/planning helpers use responsibility-based names.
- Skills live in `skills/<name>/SKILL.md`; data tools use `get_*` names.

## Security rules

- The original user access token is the sole bearer through Agent, Gateway, MCP, and Sage API.
- AgentCore managed authorizers own signature, expiry, issuer, client, local scope, token type, and exact lane tenant-claim validation.
- Agent and MCP application code must not claim to re-verify managed authentication decisions.
- Sage API independently verifies the token because it accepts both trusted issuers and owns the data boundary.
- Tenant authority never comes from prompts, model output, query parameters, or caller tenant headers.
- Browser renewal material never leaves the browser.
- No M2M, OAuth credential-provider, OBO, token-exchange, workload-token, context-token, or static-token fallback path belongs in this repository.

## Deployment rules

- Deployment configuration defaults to `scripts/identity_deployment.json` and may be overridden with `SAGE_IDENTITY_CONFIG_FILE`.
- Renderers and the deployment planner are local and mutation-free.
- AWS mutation occurs only through an explicitly invoked deploy command after configuration, rollback, and security approval.
- Preserve the IPv4 endpoint workaround in AWS deployment scripts until the macOS networking constraint is removed and verified.
