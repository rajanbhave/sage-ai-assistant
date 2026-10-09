---
inclusion: always
---

# Tech Stack and Development Conventions

## Backend

- Python 3.13+
- Strands Agents and `BedrockAgentCoreApp`
- FastMCP on port 8000 with streamable HTTP
- AgentCore Runtime for Agent and MCP hosting
- AgentCore Gateway MCP-server target with outbound OAuth `TOKEN_EXCHANGE` and DYNAMIC listing
- AgentCore Identity `CustomOauth2` credential providers configured for on-behalf-of token exchange
- Auth0, one tenant per lane, as the token issuer, with the lane's Cognito pool as its upstream OIDC connection
- PyJWT with cryptography for independent Sage API validation
- `uv` with `pyproject.toml` and `uv.lock`

### Python conventions

- Use type hints and focused docstrings on public boundaries.
- Keep model orchestration in `agent/`, MCP transport/tool registration in `mcp_server/`, shared API authorization/data in `sage_api/`, and cross-component identity primitives in `sage_identity/`.
- Use `headers: dict = CurrentHeaders()` for FastMCP request headers.
- Parse exactly one Authorization bearer at each inbound boundary. Use it only to read the principal, never as an outbound credential.
- Obtain outbound tokens through `sage_identity/downstream.py`, a thin wrapper over the AgentCore SDK `IdentityClient.get_token` with `auth_flow="ON_BEHALF_OF_TOKEN_EXCHANGE"` and the platform workload access token. One call, no retry with another credential. Never call the Auth0 token endpoint from application code.
- Use AgentCore Identity for every credential job it offers: managed inbound authorizers, workload identity, credential providers, the exchange itself and Gateway target exchange. OBO clients authenticate with `PRIVATE_KEY_JWT` backed by KMS, so no client secret exists.
- Do not put architecture route or option labels into implementation identifiers.
- Do not add dependencies when the standard library or an installed package already covers the need.

## Frontend

- React, TypeScript strict mode, Vite, Tailwind CSS, shadcn/ui
- `@auth0/auth0-spa-js`, pinned to an exact version, for lane-specific sign-in with authorization code, PKCE and rotating refresh tokens (replaces `amazon-cognito-identity-js` at cutover)
- Direct streaming to the selected Agent Runtime endpoint

### Frontend conventions

- Trusted lane configuration contains exactly Tenant_A and Tenant_B, each with its own Auth0 domain and client.
- Access tokens and renewal stay inside the authentication/session layer.
- All Agent invocation transport goes through `frontend/src/lib/agentcore-client/client.ts`.
- Conversation state is bound to session, lane, subject, and tenant; identity changes clear it.
- Render model output as safe text/Markdown, never unsanitized HTML.

## Authentication responsibilities

| Component | Responsibility |
|---|---|
| Frontend | Sign in through the lane's Auth0 tenant, validate lane and session claims, send the Agent token |
| Auth0 tenant | Issue audience-bound tokens, perform OBO exchanges, set the tenant claim from the verified Cognito value |
| Cognito pool | Federate the customer IdP and add the trusted tenant claim to the ID token Auth0 receives |
| Managed authorizers | Verify signature, expiry, issuer, audience, client, local scope, and exact lane tenant |
| Agent application | Exchange for the Gateway token and check it belongs to the same principal |
| Gateway | Exchange for the MCP token through its `TOKEN_EXCHANGE` target |
| MCP application | Extract subject and tenant, enforce hosting-lane equality, exchange for the Sage API token |
| Sage API | Independently validate both issuers, `aud`, `typ`, client and `act` chain, then enforce business and data authorization |

## Testing

| Layer | Command |
|---|---|
| Backend | `uv run pytest -q` |
| Python compile | `uv run python -m compileall -q agent mcp_server sage_api sage_identity scripts tests` |
| Frontend tests | `cd frontend && npm test` |
| Frontend build | `cd frontend && npm run build` |
| Shell syntax | `bash -n scripts/deploy_agent.sh scripts/deploy_gateway.sh scripts/deploy_mcp.sh` |

Property tests are useful for identity invariants. Focused unit tests cover the no-forwarding rule (outbound bearer never equals inbound), exchange error mapping, same-principal checks, authorizer payloads, fail-closed parsing, the Auth0 Action and API isolation.

## Deployment

Target order once the `downstream-user-grants` spec adds the new scripts:

```bash
uv run python scripts/deploy_user_pool.py            # Cognito upstream client and customizer
uv run python scripts/deploy_auth0_tenant.py         # per-lane Auth0 tenant configuration
uv run python scripts/deploy_credential_providers.py # OBO credential providers
uv run python scripts/deploy_sage_api.py
uv run python scripts/deploy_registry.py
bash scripts/deploy_mcp.sh
bash scripts/deploy_gateway.sh
bash scripts/deploy_agent.sh
```

Deployment uses `scripts/identity_deployment.json` or `SAGE_IDENTITY_CONFIG_FILE`. Rendering and dry-run planning are mutation-free; deploy commands require `--confirm`, explicit operator intent and approved AWS and Auth0 configuration. Route C deploy paths remain until retirement and must not be extended.
