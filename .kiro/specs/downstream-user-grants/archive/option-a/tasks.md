# Implementation Plan: Downstream User Grants

## Overview

Replace Route C JWT passthrough with audience-bound user tokens per hop,
obtained once and refreshed by AgentCore Identity. Phase 0 answers the open
platform questions in a scratch pool. Phase 1 delivers the direct Claude and
Codex path, onboarded only through URL elicitation. Phase 2 delivers the web
agent path and its Connect_Step. Phase 3 cuts over and retires Route C.

Route C-owned resources stay deployed and unmodified until Phase 3. Shared
lane resources change only in task 2.1, as the design's shared-resource table
lists. Every AWS mutation runs through a deploy script with `--confirm`, after
its `--render` output is reviewed. Tasks marked "operator" need the user at a
browser or connector.

A spike failure without a fallback marked "within requirements" in the design
stops the plan. Do not continue past task 0.12 until the requirements are
revised and approved.

## Tasks

- [ ] 0. Phase 0: platform spikes in a scratch pool
  - [ ] 0.1 Create the scratch environment
    - New Essentials pool with its own prefix domain on managed login v2, scratch user with a tenant assignment, scratch alias of the pre-token Lambda code with scratch configuration, scratch clients, providers, KMS key and a throwaway MCP Runtime.
    - Record every resource in a scratch section of the manifest. Touch no Shared_Resource.
    - _Requirements: 14.1, 14.4, 15.1_
  - [ ] 0.2 S1: managed login v2 resource binding (operator)
    - _Requirements: 1.2, 1.4, 1.5, 2.3, 3.1, 6.3_
  - [ ] 0.3 S2: AgentCore Cognito provider with `resources`
    - _Requirements: 5.1, 8.1_
  - [ ] 0.4 S3: return parameters, `customState` round trip, cross-workload completion, second-user rejection (operator)
    - _Requirements: 7.3, 7.6, 7.7_
  - [ ] 0.5 S4: `WorkloadAccessToken` delivery to FastMCP headers
    - _Requirements: 5.1_
  - [ ] 0.6 S5: Gateway target `customParameters.resource` gives the MCP token `aud`. `mcpToolSchema` on a Runtime MCP URL
    - _Requirements: 1.3, 10.1, 10.2, 10.3_
  - [ ] 0.7 S6: grant sharing across inbound clients
    - _Requirements: 6.6_
  - [ ] 0.8 S7: Gateway passthrough of -32042. URL elicitation in Claude and Codex from a fresh browser profile (operator)
    - _Requirements: 9.3, 9.4, 10.4_
  - [ ] 0.9 S8: confidential refresh, revocation and `forceAuthentication` with five-minute access tokens
    - _Requirements: 8.1, 8.3, 8.4_
  - [ ] 0.10 S9: public-client refresh token rotation through the token endpoint for the web app, Claude and Codex (operator)
    - _Requirements: 2.7, 2.8_
  - [ ] 0.11 S10: issuer metadata on a managed login v2 domain
    - _Requirements: 9.7, 9.8_
  - [ ] 0.12 Record outcomes in the design Decision log, get user approval for any within-requirements fallback, delete scratch resources
    - _Requirements: 16.6_

- [ ] 1. Phase 1: shared identity foundations (code only)
  - [ ] 1.1 Extend lane and issuer models
    - Resource_URLs, role client IDs, provider names, return URL and KMS key ARN on `TenantLaneConfiguration`. `audience` on `ApiIssuerConfiguration`.
    - Reject empty, duplicated or cross-lane-reused values.
    - _Requirements: 1.1, 2.4, 13.1, 13.3_
  - [ ] 1.2 Render per-door audience and clients in `managed_authorizers.py`
    - Remove `allowedWorkloadConfiguration` rendering.
    - _Requirements: 1.3, 2.4, 3.3_
  - [ ] 1.3 Add client scope ceilings to the access-token customizer
    - Keep the Route C frontend client at its current four-scope ceiling until retirement.
    - _Requirements: 2.2, 2.3, 3.1, 3.4_
  - [ ] 1.4 Add `sage_identity/downstream.py`
    - `obtain_user_grant`, `require_same_principal`, `issue_pending`, `verify_pending`. Add `IdentityErrorCode.AUTHORIZATION_REQUIRED`.
    - _Requirements: 5.1, 5.2, 5.3, 7.2, 7.6, 8.4, 12.1_
  - [ ] 1.5 Tests for 1.1 to 1.4
    - Authorizer rendering. Customizer ceiling intersection and unchanged Route C client scopes (property test). `require_same_principal` and Pending_Transaction rejection cases (property tests, KMS stubbed).
    - _Requirements: 1.3, 2.3, 5.2, 7.6, 16.4_

- [ ] 2. Phase 1: Cognito, KMS and credential providers
  - [ ] 2.1 Apply the shared-resource changes, one lane at a time, Tenant_A first
    - For each row of the design's shared-resource table: snapshot, run `validate_route_c.py`, apply, run it again, and roll back on any failure before continuing.
    - Record each snapshot reference and regression result in the evidence file.
    - _Requirements: 14.3, 16.5_
  - [ ] 2.2 Update `deploy_user_pool.py` for the five role clients per lane
    - PKCE public clients with rotation enabled and `REFRESH_TOKEN_AUTH` removed. Confidential outbound clients with rotation per S8. Approved refresh validity. Read-modify-write with readback.
    - _Requirements: 2.1, 2.5, 2.6, 2.7, 8.2, 8.3, 15.3_
  - [ ] 2.3 Add `deploy_credential_providers.py`
    - Three providers per lane, provider callback registered on each owning client, lane KMS HMAC key with `GenerateMac` for MCP and Agent roles and `VerifyMac` for the Agent role only, and `--register-return-urls` for workload identities and the Gateway target. Client secrets held in memory only.
    - _Requirements: 2.5, 7.1, 7.2, 12.4, 13.3, 15.1_
  - [ ] 2.4 Update the manifest schema, renderer and dry-run planner
    - Replace `bearerTransport`, `gatewayTarget`, source-signal and API source-path fields with `downstreamGrants`. Order each receiver as create, read URL, bind `allowedAudience`. List the shared-resource steps with their checks.
    - _Requirements: 1.1, 14.1, 14.3, 15.2_
  - [ ] 2.5 Tests for the deploy guards and renderer
    - _Requirements: 15.1, 15.3_

- [ ] 3. Phase 1: Sage API and MCP Runtime
  - [ ] 3.1 Require `aud` and the `mcp-outbound` client in `sage_api/identity.py`
    - _Requirements: 11.1, 11.2, 11.3_
  - [ ] 3.2 Replace bearer forwarding in the MCP data tools
    - Read `WorkloadAccessToken`, obtain the `api-grant` token with a Pending_Transaction token as `customState`, check the Principal, call the API with it. A missing grant raises URL elicitation. No other onboarding route.
    - _Requirements: 4.1, 4.4, 5.1, 5.2, 7.3, 9.3, 9.5_
  - [ ] 3.3 Add `get_connection_status`
    - _Requirements: 9.6_
  - [ ] 3.4 Tests for 3.1 to 3.3
    - Outbound bearer never equals inbound bearer. Missing grant never yields a URL in tool text. API rejects missing or wrong `aud`, wrong client, ID token, wrong tenant, expiry and scope.
    - _Requirements: 4.5, 9.5, 11.3, 12.1_
  - [ ] 3.5 Update `deploy_mcp.sh` and `deploy_sage_api.py`
    - Door-table authorizer, provider, return URL and KMS env, role permissions from S2. New Sage API instance with distinct names.
    - _Requirements: 1.3, 2.4, 14.1, 15.1_

- [ ] 4. Phase 1: web sign-in, return page and completion action
  - [ ] 4.1 Replace SRP sign-in with managed login code grant and PKCE
    - Validate issuer, client, `token_use`, tenant and `aud`. Browser-only token-endpoint refresh that stores the rotated refresh token. Remove `amazon-cognito-identity-js`.
    - _Requirements: 1.2, 2.7, 8.5, 13.1_
  - [ ] 4.2 Add the `/oauth/return/<lane>` page
    - Popup path: same-origin postMessage to the opener. Fresh-tab path: save the session URI and Pending_Transaction token in this tab's `sessionStorage`, sign in with a bound `state`, restore on matching callback, show the confirmation screen, then complete. Reject a return with no `state` and no opener.
    - _Requirements: 7.3, 7.4, 7.5, 7.8, 7.9_
  - [ ] 4.3 Add the Agent `complete_authorization` action
    - Bounded `session_uri` and `pending`. `verify_pending` against the hosting lane and inbound Principal before `CompleteResourceTokenAuth`. No call and no retry on failure. Unknown actions rejected.
    - _Requirements: 7.6, 7.7, 7.8_
  - [ ] 4.4 Update `deploy_agent.sh` for the new Agent Runtime authorizer, env and permissions
    - _Requirements: 2.4, 14.1, 15.1_
  - [ ] 4.5 Tests for 4.1 to 4.3 (Vitest and pytest)
    - Fresh-tab save and restore across sign-in, mismatched sign-in `state`, confirmation without an opener, tampered and expired Pending_Transaction, other-user Pending_Transaction.
    - _Requirements: 7.4, 7.5, 7.6, 7.7, 16.4_
  - [ ] 4.6 Retarget `configure_claude_oauth.py` to the `connector` client
    - _Requirements: 9.1_
  - [ ] 4.7 Add the metadata and rotation checks to `validate_downstream_grants.py`
    - Fixture tests for metadata with and without `code_challenge_methods_supported`.
    - _Requirements: 2.7, 9.7, 9.8_

- [ ] 5. Phase 1 gate
  - [ ] 5.1 Deploy Phase 1 resources for both lanes (render, review, then confirm)
    - _Requirements: 14.1, 14.2, 15.1_
  - [ ] 5.2 Scripted checks with `validate_downstream_grants.py`
    - Cross-lane, wrong-client, no-`aud`, expired and ID tokens at the MCP door and the API. Metadata check. Public-client rotation check.
    - _Requirements: 1.6, 2.7, 9.7, 13.2, 16.2, 16.4_
  - [ ] 5.3 Operator run with native Claude and Codex connectors on both lanes, from a fresh browser profile
    - First tool call triggers URL elicitation, the fresh-tab return completes after sign-in and confirmation, and the retried call reads product and claim data. MCP and API tokens differ with their own `aud`. Revoked grant recovery. Second-user and tampered-state completion attempts fail.
    - _Requirements: 9.3, 16.1, 16.4_
  - [ ] 5.4 Record the metadata outcome under Requirement 9.8
    - If it fails, record it as a non-compliance and obtain the user's recorded risk acceptance before any connector use beyond isolated testing.
    - _Requirements: 9.8, 16.2_

- [ ] 6. Phase 2: Gateway and agent path
  - [ ] 6.1 Rewrite `deploy_gateway.py` for an MCP-server target with `AUTHORIZATION_CODE`
    - Rendered `mcpToolSchema`, DEFAULT listing, `defaultReturnUrl`, `customParameters.resource`. Delete every `JWT_PASSTHROUGH` code path.
    - _Requirements: 4.3, 10.1, 10.2, 10.3_
  - [ ] 6.2 Implement `connect` and `chat` in `agent/agent.py`
    - Obtain the `gateway-grant` token with a Pending_Transaction `customState`, check the Principal, status preflight, convert elicitations to `authorization_required` with a Pending_Transaction token (minted for `gateway_mcp`, relayed for `mcp_api`), exclude the status tool from the model.
    - _Requirements: 4.2, 4.4, 5.2, 7.3, 10.4, 10.5_
  - [ ] 6.3 Add the Connect_Step to the web app
    - Silent check on load, Connect button on demand, one reused popup, bounded loop, one held Pending_Transaction token with its hop and popup reference, per-hop return acceptance (matching `state` for `agent_gateway` and `mcp_api`, popup source, origin and held token for `gateway_mcp`), hop-coded failures.
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 7.3, 7.9, 7.10_
  - [ ] 6.4 Update the agent client parser and demo stage for per-hop tokens
    - _Requirements: 6.5, 12.2_
  - [ ] 6.5 Tests for 6.1 to 6.4
    - Outbound bearer never equals inbound. Elicitation URL never reaches the model. Status tool absent from model tools. Connect loop bound.
    - Return acceptance (Vitest): `gateway_mcp` return without `state` completes and sends the held token to `complete_authorization`. `gateway_mcp` rejected for another source window, another origin, no held token, a token for another hop, or an expired token. `agent_gateway` and `mcp_api` rejected for missing or different `state`.
    - Agent (pytest): `complete_authorization` succeeds for a valid `gateway_mcp` token with no returned `state` involved.
    - _Requirements: 4.5, 7.9, 7.10, 10.4, 10.5, 12.1_

- [ ] 7. Phase 2 gate
  - [ ] 7.1 Deploy Phase 2 resources for both lanes (render, review, then confirm)
    - _Requirements: 14.1, 15.1_
  - [ ] 7.2 Scripted negative checks at the Agent and Gateway doors
    - _Requirements: 13.2, 16.4_
  - [ ] 7.3 Operator run in the web app on both lanes
    - One Connect_Step, then product and claim reads. A new browser session on a later day signs in and performs no Connect_Step redirects. Revoked grant recovery. Record whether S6 sharing let the connector skip elicitation.
    - _Requirements: 6.3, 6.4, 6.6, 8.1, 16.3, 16.4_
  - [ ] 7.4 Re-run `validate_route_c.py` on both lanes to confirm Route C still works before cutover
    - _Requirements: 14.2, 16.5_

- [ ] 8. Phase 3: cutover and Route C retirement
  - [ ] 8.1 Tag the last Route C commit
    - _Requirements: 14.8_
  - [ ] 8.2 Cut the frontend over to the new lane records and record the rollback values
    - _Requirements: 14.5_
  - [ ] 8.3 Delete Route C cloud resources after explicit operator confirmation
    - Runtimes, Gateways, targets, the Route C Sage API instance and the Route C frontend and Claude test clients. Remove the Route C client from customizer ceilings.
    - _Requirements: 14.6_
  - [ ] 8.4 Remove Route C-only code and tests
    - `validate_route_c.py`, `deployment_evidence.py` source-signal types, `test_source_signal_candidate.py`, `JWT_PASSTHROUGH` constants, validation scope canaries, and forwarding tests replaced in 3.4 and 6.5.
    - _Requirements: 14.6_
  - [ ] 8.5 Update steering, README and docs
    - `product.md`, `structure.md`, `tech.md`, README identity sections, `docs/emil-authentication-options.md` results including the metadata outcome and the note that Emil's proxy removal still needs Emil's own validation, and mark `multi-tenant-agent-identity` as superseded for bearer transport.
    - _Requirements: 14.7_
  - [ ] 8.6 Final verification
    - `uv run pytest -q`, compileall, `bash -n` on deploy scripts, `npm test`, `npm run build`, `git diff --check`.
    - _Requirements: 16.6_
