# Implementation Plan: OBO Token Exchange (Option B1)

## Overview

Replace Route C JWT passthrough with Auth0 OBO token exchange at every hop.
Phase 0 answers the open platform questions with scratch resources. Phase 1
delivers the direct Claude and Codex path. Phase 2 delivers the web agent path.
Phase 3 cuts over and retires Route C.

Route C-owned resources stay deployed and unmodified until Phase 3. Shared lane
resources change only in task 2.1, as the design's shared-resource table
lists. Every AWS or Auth0 mutation runs through a deploy script with
`--confirm`, after its `--render` output is reviewed. Tasks marked "operator"
need the user at a browser or connector.

A spike failure without a fallback marked "within requirements" in the design
stops the plan. Do not continue past task 0.15 until the requirements are
revised and approved.

## Tasks

- [ ] 0. Phase 0: platform spikes with scratch resources
  - [ ] 0.1 Create the scratch environment
    - Scratch Cognito Essentials pool with its own domain, scratch user with a tenant assignment, scratch alias of the pre-token Lambda code with scratch configuration.
    - Scratch Auth0 tenant (operator creates it, scripts configure it), scratch AgentCore providers and a throwaway MCP Runtime.
    - Record every resource in a scratch section of the manifest. Touch no Shared_Resource.
    - _Requirements: 15.1, 15.4, 16.1_
  - [ ] 0.2 S1: Auth0 OIDC connection through Cognito, claim mapping, `sub` format (operator)
    - _Requirements: 1.2, 1.3, 4.1, 4.2_
  - [ ] 0.3 S2: Action sets the exact `custom:tenant_id` and `cognito_sub` at sign-in, refresh and exchange, and identifies the target API, removes scopes and denies on an exchange
    - _Requirements: 4.3, 4.4, 4.5, 4.7, 4.8, 18.4_
  - [ ] 0.4 S3: AgentCore `CustomOauth2` OBO exchange against Auth0 with a Custom API client and client grant, subject token type recorded, wrong-audience exchange refused
    - _Requirements: 3.9, 3.10, 3.12, 6.1, 6.3, 7.1_
  - [ ] 0.5 S4: AgentCore authorizer accepts Auth0 RFC 9068 tokens with audience, client, scope and claim rules
    - _Requirements: 2.2, 2.3, 2.4, 3.3, 3.4_
  - [ ] 0.6 S5: `WorkloadAccessToken` in FastMCP headers with an Auth0 inbound token, IAM recorded
    - _Requirements: 6.1_
  - [ ] 0.7 S6: Gateway MCP-server target with `TOKEN_EXCHANGE` and DYNAMIC listing
    - _Requirements: 10.1, 10.2, 10.3_
  - [ ] 0.8 S7: Claude and Codex with a pre-registered Auth0 public client (operator)
    - _Requirements: 3.7, 9.1, 9.6_
  - [ ] 0.9 S8: exchange count, latency and reuse per chat turn and per tool call
    - _Requirements: 14.1, 14.2_
  - [ ] 0.10 S9: public-client refresh token rotation and reuse detection
    - _Requirements: 3.6_
  - [ ] 0.11 S10: Auth0 metadata, PKCE and RFC 9207
    - _Requirements: 9.3_
  - [ ] 0.12 S11: blocked and disabled user behaviour for fresh exchange, refresh and sign-in, residual token window, sign-out refresh token revocation
    - _Requirements: 8.4, 8.5, 8.6_
  - [ ] 0.13 S12: AgentCore `PRIVATE_KEY_JWT` provider authenticating to Auth0 for OBO
    - _Requirements: 3.5_
  - [ ] 0.14 S13: signing key rotation and revocation against the Sage API and the managed authorizers
    - _Requirements: 11.5_
  - [ ] 0.15 Record outcomes in the design Decision log, get user approval for any within-requirements fallback, delete scratch resources
    - _Requirements: 17.6_

- [ ] 1. Phase 1: shared identity foundations (code only)
  - [ ] 1.1 Extend lane and issuer models for Auth0 issuers, API identifiers, role clients, providers and the Cognito upstream client
    - Reject empty, duplicated or cross-lane-reused values.
    - _Requirements: 1.5, 2.1, 3.4, 13.2_
  - [ ] 1.2 Render the Door table in `managed_authorizers.py`
    - Remove the `token_use` rule and `allowedWorkloadConfiguration`.
    - _Requirements: 2.3, 3.4, 4.7_
  - [ ] 1.3 Add the `sage-<lane>-auth0` client to the Cognito customizer's trusted clients
    - Route C clients keep their current scopes until retirement.
    - _Requirements: 4.1_
  - [ ] 1.4 Add `sage_identity/downstream.py`: `exchange_for` as a thin wrapper over the AgentCore SDK `IdentityClient.get_token` OBO flow, `require_same_principal`, and the new error codes
    - _Requirements: 6.1, 6.4, 6.5, 6.6, 14.3_
  - [ ] 1.5 Add `auth0/actions/post_login.js` and `auth0/tenant.template.json`
    - Action: tenant claim, `cognito_sub`, revoked flag, and permission map enforcement.
    - Template: Custom API clients with `resource_server_identifier`, OBO profile, the five user-delegated client grants, and `require_client_grant` / `deny_all` on every API.
    - Manifest gains the lane `permissionMap`.
    - _Requirements: 1.2, 2.4, 2.5, 3.1, 3.2, 3.3, 3.8, 3.9, 3.10, 3.11, 4.3, 4.4, 4.5, 8.5, 18.3, 18.4_
  - [ ] 1.6 Tests for 1.1 to 1.5
    - Authorizer rendering. `require_same_principal` property test. `exchange_for` single call and error mapping. Node test for the Action (missing tenant, wrong lane, wrong connection, revoked flag, no mapped group, group lacking the target scope, scope removal, unknown API, success). Template test: no API left on `allow_all`, no client grant beyond the five, each OBO client bound to its incoming API.
    - _Requirements: 2.3, 3.9, 3.10, 3.11, 4.4, 6.5, 6.6, 18.4_

- [ ] 2. Phase 1: Cognito, Auth0 and credential providers
  - [ ] 2.1 Apply the shared-resource changes, one lane at a time, Tenant_A first
    - For each row of the design's shared-resource table: snapshot, run `validate_route_c.py`, apply, run it again, and roll back on any failure before continuing. Record results in the evidence file.
    - _Requirements: 15.3, 17.5_
  - [ ] 2.2 Add `deploy_auth0_tenant.py`
    - Per lane: tenant settings, connection (including the `cognito:groups` mapping), APIs with access policies (created as receivers come up), applications and Custom API clients, client grants, Action and binding. Session and refresh token absolute lifetime set to the approved ceiling (at most 12 hours) and profile sync at each login enabled. Read-modify-write with readback that fails on any extra client grant, an API left on `allow_all`, or a session lifetime above the ceiling. Management credentials in memory only.
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.4, 2.5, 3.1, 3.2, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 12.3, 16.1, 16.3, 18.2, 18.7, 18.8_
  - [ ] 2.3 Add `deploy_credential_providers.py`
    - Per OBO client: KMS signing key and key policy, public key registered in Auth0, `CustomOauth2` OBO provider with `PRIVATE_KEY_JWT` and the S3 and S12 settings. No secret read or written unless the S12 fallback applies.
    - _Requirements: 3.5, 6.1, 6.3, 12.1, 13.2_
  - [ ] 2.4 Update the manifest schema, renderer and dry-run planner
    - Replace Route C fields with the `obo` block. Order each receiver as create, read URL, create Auth0 API, bind `allowedAudience`. List the shared-resource steps with their checks.
    - _Requirements: 2.1, 15.1, 15.3, 16.2_
  - [ ] 2.5 Tests for the deploy guards and renderer
    - _Requirements: 16.1, 16.3_

- [ ] 3. Phase 1: Sage API and MCP Runtime
  - [ ] 3.1 Validate Auth0 tokens in `sage_api/identity.py`
    - Auth0 issuer allowlist, `aud`, `typ`, `client_id`, `act` head, scope, tenant against issuer lane. Remove the `token_use` check.
    - Run-time JWKS per issuer through PyJWT `PyJWKClient`, bounded cache, rate-limited refresh on unknown `kid`, fail closed.
    - _Requirements: 7.2, 11.1, 11.2, 11.3, 11.4, 11.5_
  - [ ] 3.2 Replace bearer forwarding in the MCP data tools with `exchange_for`
    - Read `WorkloadAccessToken`, exchange with the API provider, check the Principal, call the API with the exchanged token.
    - _Requirements: 5.1, 5.4, 6.1, 6.5, 9.4_
  - [ ] 3.3 Read `cognito_sub` and record the inbound client in `mcp_server/identity.py`
    - _Requirements: 6.5, 7.3, 7.4_
  - [ ] 3.4 Tests for 3.1 to 3.3
    - Outbound bearer never equals inbound. API rejects every token kind listed in Requirement 11.4 and every failed check in 11.1. JWKS rotation, removal, fetch failure and refresh rate limit with a stubbed JWKS.
    - _Requirements: 5.5, 9.5, 11.4, 11.5, 12.1_
  - [ ] 3.5 Update `deploy_mcp.sh` and `deploy_sage_api.py`
    - Door-table authorizer, provider env, IAM from S5. New Sage API instance with distinct names and Auth0 JWKS keys.
    - _Requirements: 2.3, 3.4, 15.1, 16.1_
  - [ ] 3.6 Retarget `configure_claude_oauth.py` to the Auth0 `connector` client
    - _Requirements: 9.1_
  - [ ] 3.7 Add `validate_obo.py` with config readback, metadata check, rotation check and negative token checks
    - Fixture tests for metadata with and without `S256`.
    - _Requirements: 3.6, 9.3, 17.4_

- [ ] 4. Phase 1 gate
  - [ ] 4.1 Deploy Phase 1 resources for both lanes (render, review, then confirm)
    - _Requirements: 15.1, 15.2, 16.1_
  - [ ] 4.2 Scripted checks with `validate_obo.py` at the MCP door and the API
    - _Requirements: 9.3, 13.1, 17.2, 17.4_
  - [ ] 4.3 Operator run with native Claude and Codex connectors on both lanes, from a fresh browser profile
    - Sign-in through Auth0 and Cognito, product and claim reads, connector and API tokens differ with their own `aud`, API token has tenant claim, `cognito_sub` and an `act` chain naming the MCP OBO client.
    - A second user in the same lane without the API permission is refused at the MCP to API exchange.
    - Wrong-audience exchanges refused. Blocked user's next fresh exchange, refresh and sign-in fail, and residual access ends within the approved window.
    - Permission removal: remove a demo user's group in Cognito, force a new interactive sign-in, and confirm the new tokens lack the removed scope and the MCP to API exchange is refused. Record that a refresh before re-sign-in still carries the old scope (the documented limitation).
    - _Requirements: 3.12, 6.7, 8.6, 9.1, 9.4, 17.1, 17.4, 17.7, 17.9, 18.4, 18.7, 18.8_

- [ ] 5. Phase 2: Gateway, agent and web app
  - [ ] 5.1 Rewrite `deploy_gateway.py` for an MCP-server target with `TOKEN_EXCHANGE` and DYNAMIC listing
    - Delete every `JWT_PASSTHROUGH` code path.
    - _Requirements: 5.3, 10.1, 10.2, 10.3_
  - [ ] 5.2 Replace bearer forwarding in `agent/agent.py` with `exchange_for` for the Gateway token
    - _Requirements: 5.2, 5.4, 6.1, 6.5, 10.4_
  - [ ] 5.3 Update `deploy_agent.sh` for the new Agent Runtime authorizer, env and permissions
    - _Requirements: 2.3, 3.4, 15.1, 16.1_
  - [ ] 5.4 Replace Cognito SRP sign-in with Auth0 in the web app
    - `lib/auth/auth0.ts` with `@auth0/auth0-spa-js` pinned to an exact version, lane records with Auth0 domain and client, explicit `scope` on every token request, token validation before use, sign-out that revokes the refresh token at `/oauth/revoke` and then ends the Auth0 session. Remove `amazon-cognito-identity-js`.
    - _Requirements: 8.1, 8.2, 8.4, 13.1_
  - [ ] 5.5 Update the demo stage to show four distinct tokens with `aud`, `client_id` and `act`
    - _Requirements: 7.1, 12.2_
  - [ ] 5.6 Tests for 5.1 to 5.5
    - Outbound bearer never equals inbound in the Agent. Frontend token validation and lane isolation.
    - _Requirements: 5.5, 13.1_

- [ ] 6. Phase 2 gate
  - [ ] 6.1 Deploy Phase 2 resources for both lanes (render, review, then confirm)
    - _Requirements: 15.1, 16.1_
  - [ ] 6.2 Scripted negative checks at the Agent and Gateway doors
    - _Requirements: 13.1, 17.4_
  - [ ] 6.3 Operator run in the web app on both lanes
    - One sign-in, product and claim reads, no screen after sign-in, four distinct tokens observed. Sign-out, then confirm the old refresh token is rejected and the next sign-in shows no extra step.
    - Same-lane user without the API permission gets a stable error in chat and no Sage API call.
    - _Requirements: 6.7, 8.4, 17.3, 17.7, 17.8, 18.4_
  - [ ] 6.4 Re-run `validate_route_c.py` on both lanes to confirm Route C still works before cutover
    - _Requirements: 15.2, 17.5_

- [ ] 7. Phase 3: cutover and Route C retirement
  - [ ] 7.1 Tag the last Route C commit
    - _Requirements: 15.8_
  - [ ] 7.2 Cut the frontend over to the Auth0 lane records and record the rollback values
    - _Requirements: 15.5_
  - [ ] 7.3 Delete Route C cloud resources after explicit operator confirmation
    - Runtimes, Gateways, targets, the Route C Sage API instance and the Route C Cognito clients. Remove those clients from the customizer.
    - _Requirements: 15.6_
  - [ ] 7.4 Remove Route C-only code and tests
    - `validate_route_c.py`, source-signal types in `deployment_evidence.py`, `test_source_signal_candidate.py`, `JWT_PASSTHROUGH` constants, validation scope canaries, and forwarding tests replaced in 3.4 and 5.6.
    - _Requirements: 15.6_
  - [ ] 7.5 Update steering, README and docs
    - Steering was moved to the OBO model on 9 October 2026. At retirement, remove its Route C transition notes from `product.md`, `structure.md` and `tech.md`. Update README identity sections, `docs/emil-authentication-options.md` with results and the note that Emil's proxy removal still needs Emil's own validation, and mark `multi-tenant-agent-identity` as superseded for bearer transport.
    - _Requirements: 15.7_
  - [ ] 7.6 Final verification
    - `uv run pytest -q`, compileall, `bash -n` on deploy scripts, `npm test`, `npm run build`, the Action test, `git diff --check`.
    - _Requirements: 17.6_
