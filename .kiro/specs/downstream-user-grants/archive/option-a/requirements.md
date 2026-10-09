# Requirements Document

## Introduction

This feature replaces Sage's JWT passthrough design (Route C) with separately
issued, audience-bound user access tokens at every hop. It implements Option A
from `docs/emil-authentication-options.md`: Cognito authorization-code grants
obtained once per downstream resource, stored and refreshed by AgentCore
Identity, and retrieved by each workload for the authenticated user.

Route C forwards the browser's Cognito access token unchanged through Agent,
Gateway, MCP and Sage API. The MCP authorization specification forbids an MCP
server from passing its received token to a downstream API. Sage
`mcp_server/sage_api_client.py` does exactly that today. This feature removes
that forwarding and the Gateway `JWT_PASSTHROUGH` target.

Two paths are in scope and are delivered in two phases:

```text
Phase 1  Claude/Codex -> MCP Runtime -> Sage API
Phase 2  Sage web app -> Agent Runtime -> Gateway -> MCP Runtime -> Sage API
```

Consent is collected once. Cognito managed login has no consent page, so each
grant is a browser redirect that completes without user input while the user
holds a Cognito managed-login session. The web app runs every missing grant in
one Connect step right after sign-in. AgentCore Identity then refreshes each
grant silently until its refresh token expires or is revoked.

Sage remains the proof of concept for Emil. The Sage API already accepts only
access tokens, so Emil's legacy ID-token validator is out of scope here. The
evidence this feature produces is what Emil needs before removing its proxy:
distinct per-hop tokens, preserved tenant claims, grant reuse and refresh, and
rejection of wrong-resource, wrong-tenant and wrong-user requests. Passing these
gates validates the pattern only. It does not authorize removing Emil's proxy,
which still needs Emil's own API validator change and real Okta or Entra
federation tests.

Platform behaviour this design relies on but AWS does not document (resource
forwarding by the Gateway, cross-workload completion, grant sharing, refresh
and rotation) is treated as an unproven assumption until a Phase 0 spike
passes. A spike fallback that would change any requirement below is not a
fallback. It blocks the design until the requirements and security analysis
are revised and approved.

## Scope Boundary

### In scope

- Exactly two lanes, Tenant_A and Tenant_B, each with its own Cognito pool,
  Agent Runtime, Gateway, MCP Runtime and credential providers.
- Cognito managed login (version 2) with RFC 8707 resource binding for every
  user token, and per-role app clients with least-privilege scope ceilings.
- AgentCore Identity Cognito OAuth2 credential providers for Agent to Gateway,
  Gateway to MCP and MCP to Sage API.
- A Gateway MCP-server target using the `AUTHORIZATION_CODE` grant.
- A one-time Connect step in the web app and a session-bound completion action,
  with a per-lane KMS HMAC key for Pending_Transaction tokens.
- Audience, client, scope, token type and tenant enforcement at every door.
- Cutover from Route C, a rollback path, and retirement of Route C code,
  configuration and documentation.

### Out of scope

- Token exchange or on-behalf-of flows (Option B). Cognito does not offer them.
- Emil's API, Emil's proxy and real Okta or Entra federation. These are
  recorded as follow-up validation for Emil, not Sage deliverables.
- A third tenant, dynamic tenancy, write operations and new data tools.
- The AWS-managed consent portal. It covers only Gateway targets and cannot
  complete the Agent or MCP grants, so one Sage callback serves all three.
- Machine-to-machine credentials, static tokens and shared service tokens.

## Glossary

- **Lane**: One of Tenant_A or Tenant_B and all resources bound to it.
- **Hop**: One caller-to-receiver boundary. The hops are Web to Agent, Agent to
  Gateway, Gateway to MCP, Connector to MCP and MCP to API.
- **Resource_URL**: The URL a token is requested for. Cognito copies it into
  the access token `aud` claim. Each hop receiver has exactly one per lane.
- **Door**: A receiver that validates an inbound token. The doors are the Agent
  Runtime, Gateway and MCP Runtime managed authorizers and the Sage API code.
- **Web_Client**: The public Cognito client used by the Sage browser app.
- **Connector_Client**: The public Cognito client used by Claude and Codex.
- **Outbound_Client**: A confidential Cognito client owned by one credential
  provider. Each lane has three: Agent, Gateway and MCP outbound clients.
- **Grant**: A stored authorization for one user, one workload and one
  credential provider, held in the AgentCore Identity token vault.
- **Connect_Step**: The web app flow that obtains every missing grant once.
- **Principal**: The verified pair of issuer and subject, plus the signed
  tenant claim `custom:tenant_id`.
- **Workload_Access_Token**: The AWS-signed opaque token AgentCore Runtime and
  Gateway deliver to a workload for calling AgentCore Identity.
- **Pending_Transaction**: A short-lived, Sage-signed value that ties one
  authorization flow to its lane, hop and initiating Principal, so the return
  page and the Agent can verify a completion without prior browser state.
- **Shared_Resource**: A resource used by both Route C and this design during
  migration: each lane's Cognito pool, its domain and its pre-token Lambda.

## Requirements

### Requirement 1: Audience-bound user token at every hop

**User Story:** As a security reviewer, I want each hop to receive a token
issued for that receiver only, so that a token stolen or replayed at one hop is
rejected at every other hop.

#### Acceptance Criteria

1. THE System SHALL define exactly one Resource_URL per Door per lane, and all
   eight Resource_URLs SHALL be distinct.
2. WHEN any user token is requested, THE requester SHALL include exactly one
   `resource` parameter equal to the receiving Door's Resource_URL.
3. EACH Door SHALL reject a token whose `aud` is absent or differs from its
   own Resource_URL before any protected behavior runs.
4. WHEN a refresh grant renews a token, THE renewed token SHALL carry the same
   `aud` as the original grant.
5. THE MCP Resource_URL SHALL equal the MCP Runtime URL that the Runtime
   advertises as `resource` in its protected-resource metadata.
6. A token issued through SDK password or SRP authentication SHALL be rejected
   at every Door because it carries no `aud`.

### Requirement 2: Least-privilege clients and scopes

**User Story:** As a tenant administrator, I want each client to obtain only
the scope for the one hop it serves, so that no token authorizes more than one
receiver.

#### Acceptance Criteria

1. EACH lane SHALL have exactly five app clients for this design: Web_Client,
   Connector_Client and three Outbound_Clients, each with a single scope
   ceiling.
2. THE scope ceilings SHALL be `sage-agent/invoke` for Web_Client,
   `sage-mcp/invoke` for Connector_Client and the Gateway Outbound_Client,
   `sage-gateway/invoke` for the Agent Outbound_Client and `sage-api/read` for
   the MCP Outbound_Client. `openid` MAY be added where a flow requires it.
3. THE access-token customizer SHALL emit only the intersection of the user's
   administratively granted scopes and the issuing client's scope ceiling.
4. EACH Door SHALL accept only the client IDs assigned to it: Agent Runtime
   accepts Web_Client, Gateway accepts the Agent Outbound_Client, MCP Runtime
   accepts the Gateway Outbound_Client and Connector_Client, and Sage API
   accepts the MCP Outbound_Client.
5. Outbound_Clients SHALL be confidential, SHALL allow only the authorization
   code grant, and SHALL register only their own credential provider callback.
6. Public clients SHALL require S256 PKCE and SHALL have no client secret.
7. Web_Client and Connector_Client SHALL enable Cognito refresh token rotation.
   Each refresh through the grant these clients use SHALL return a new refresh
   token and invalidate the previous one after a grace period of at most 60
   seconds.
8. IF Cognito does not rotate refresh tokens on the token-endpoint refresh
   grant used by Claude, Codex or the web app, THEN that client path SHALL NOT
   pass its phase gate.

### Requirement 3: Tenant claim preserved in every token

**User Story:** As a tenant data owner, I want every downstream token to carry
the same signed tenant claim, so that tenant authorization never depends on
anything other than Cognito.

#### Acceptance Criteria

1. THE `V2_0` pre-token customizer SHALL emit `custom:tenant_id` for every
   client in the lane, on initial issuance and on refresh.
2. THE claim name and value SHALL remain configuration, unchanged from Route C.
3. EACH Door SHALL require `token_use` equal to `access` and `custom:tenant_id`
   equal to its lane tenant.
4. IF the trusted tenant assignment is missing, duplicated or disagrees with
   the lane, THEN THE customizer SHALL refuse issuance.

### Requirement 4: No forwarding of a received token

**User Story:** As an MCP server operator, I want Sage to comply with the MCP
rule against token passthrough, so that the received credential never reaches
a downstream service.

#### Acceptance Criteria

1. THE MCP application SHALL NOT send its inbound bearer to the Sage API.
2. THE Agent application SHALL NOT send its inbound bearer to the Gateway.
3. THE Gateway target SHALL NOT use `JWT_PASSTHROUGH`.
4. THE Agent and MCP applications SHALL use the inbound bearer only to read the
   Principal and, in the Agent, to prove the user to AgentCore Identity when
   completing an authorization.
5. A unit test SHALL fail if any outbound request from Agent or MCP code
   carries a bearer equal to the inbound bearer.

### Requirement 5: Downstream grant retrieval bound to the same Principal

**User Story:** As a security reviewer, I want each workload to use only a
downstream token for the same user and tenant it received, so that a stored
grant can never act for someone else.

#### Acceptance Criteria

1. THE Agent and MCP applications SHALL obtain downstream tokens from AgentCore
   Identity with the `USER_FEDERATION` flow, the Workload_Access_Token supplied
   by the platform, the hop's credential provider, scope and Resource_URL.
2. BEFORE using a downstream token, THE workload SHALL verify that its issuer,
   subject and tenant equal the inbound Principal and that its `aud` equals the
   requested Resource_URL. IF any differ, THEN THE workload SHALL discard the
   token and fail with a stable non-secret error.
3. THE credential provider name, scope and Resource_URL SHALL come from trusted
   deployment configuration and SHALL NOT be selectable by prompts, tool
   arguments, request headers or model output.
4. Grants SHALL be keyed by the AgentCore Identity tuple of workload, issuer
   and subject, and credential provider. Subjects SHALL NOT be treated as
   unique across lanes.

### Requirement 6: One-time Connect step

**User Story:** As a Sage user, I want to approve access once after my first
sign-in, so that I am not shown sign-in or consent screens on later visits.

#### Acceptance Criteria

1. WHEN a signed-in web user has any missing or unusable grant, THE web app
   SHALL run the Connect_Step before enabling chat.
2. THE Connect_Step SHALL obtain every missing grant for the lane in one user
   action, using a single popup window that it navigates through each
   authorization URL in turn.
3. WHILE the user holds a Cognito managed-login session, EACH authorization
   redirect SHALL complete without a credential prompt.
4. WHEN every grant is present, THE Connect_Step SHALL make no redirects and
   SHALL complete without visible UI.
5. THE web app SHALL show the user which lane is being connected and SHALL
   report a failed hop by stable code, never by token or URL contents.
6. WHERE spike S6 shows grants are shared across inbound clients, THE MCP to
   API grant obtained through the web app MAY also serve the same user's direct
   Claude or Codex calls. The direct path SHALL NOT depend on this. It SHALL
   establish its own grant as Requirement 9 describes.

### Requirement 7: Session-bound authorization completion

**User Story:** As a security reviewer, I want an authorization to complete
only for the same signed-in user who started it, so that a forwarded
authorization link cannot grant access to another person.

#### Acceptance Criteria

1. EACH workload identity and the Gateway target SHALL register exactly one
   allowed return URL, the web app `/oauth/return/<lane>` page of the same
   lane.
2. EVERY completion SHALL carry a Pending_Transaction token: a Sage-signed,
   lane-bound value containing the lane, the hop, a hash of the initiating
   Principal's issuer and subject, an issue time, an expiry of at most ten
   minutes and a random nonce, authenticated with the lane's KMS HMAC key.
3. FOR hops whose initiating workload controls `customState` (Agent to
   Gateway, MCP to API), THE Pending_Transaction token SHALL be the
   `customState`, so it returns to `/oauth/return/<lane>` in the redirect and
   needs no browser storage to exist beforehand. FOR the Gateway to MCP hop,
   THE Agent SHALL issue the Pending_Transaction token in its
   `authorization_required` event.
4. WHEN `/oauth/return/<lane>` loads without a web session in that lane, THE
   page SHALL store the session URI and Pending_Transaction token in the same
   tab's `sessionStorage`, start web sign-in with its own `state` bound to that
   record, and restore the record only after a sign-in callback whose `state`
   matches.
5. WHEN `/oauth/return/<lane>` was not opened by the web app's own popup, THE
   page SHALL show the lane display name, the signed-in username and the hop
   being approved, and SHALL complete only after the user confirms.
6. THE completion SHALL be performed by the Agent Runtime
   `complete_authorization` action. BEFORE calling `CompleteResourceTokenAuth`,
   THE action SHALL verify the Pending_Transaction MAC, expiry and lane, and
   that its Principal hash equals the hash of the Agent's validated inbound
   bearer. It SHALL then call `CompleteResourceTokenAuth` with the session URI
   and that bearer as the user identifier.
7. IF verification fails, or AgentCore Identity reports a user mismatch or an
   expired or unknown session URI, THEN THE action SHALL fail closed with a
   stable code and SHALL NOT call or retry `CompleteResourceTokenAuth`.
8. THE session URI SHALL be accepted only as an opaque bounded string and SHALL
   never select a lane, provider or user.
9. THE web app SHALL accept a return only by the rule for its hop:
   - FOR Agent to Gateway and MCP to API, the returned `state` SHALL be present
     and SHALL equal the Pending_Transaction token issued for that flow. A
     missing or different `state` SHALL be rejected.
   - FOR Gateway to MCP, no returned `state` is required. The opener SHALL
     accept the return only when the message comes from the popup window it
     opened, its origin equals the web app origin, and it holds an active,
     unexpired Pending_Transaction token for the `gateway_mcp` hop. Completion
     SHALL use that held token. Any `state` in the return SHALL be ignored for
     this hop.
   - A return with no `state` outside the web app popup SHALL be rejected.
10. THE web app SHALL hold at most one active Pending_Transaction at a time and
    SHALL clear it on completion, failure, popup close or expiry.

### Requirement 8: Silent reuse and refresh

**User Story:** As a Sage user, I want later requests to reuse my stored
approvals, so that normal use never interrupts me.

#### Acceptance Criteria

1. WHEN a grant holds a valid access token or refresh token, THE workload SHALL
   obtain a token without any user interaction.
2. Outbound_Client refresh token validity SHALL be an approved deployment value
   recorded with its approval reference. It determines how often reconnection
   is needed.
3. Refresh token rotation SHALL be disabled for Outbound_Clients unless spike
   S8 proves AgentCore Identity stores rotated refresh tokens. This exception
   applies only to confidential clients. Public clients follow Requirement 2.7.
4. IF a grant is revoked, expired or rejected downstream, THEN THE request
   SHALL fail with `authorization_required` and THE web app SHALL rerun the
   Connect_Step. A workload MAY re-request the same grant once with
   `forceAuthentication` to obtain a fresh authorization URL. No hop SHALL
   retry with a different credential.
5. THE web app SHALL renew its own access token through the refresh grant in
   the browser. Renewal material SHALL never leave the browser.

### Requirement 9: Direct Claude and Codex path

**User Story:** As a Claude or Codex user, I want to connect Sage's MCP server
with native OAuth, so that I can use Sage tools without the web app's chat.

#### Acceptance Criteria

1. THE connector SHALL authenticate through Cognito managed login with the
   Connector_Client, S256 PKCE and `resource` equal to the MCP Resource_URL.
2. THE MCP Runtime SHALL advertise protected-resource metadata whose `resource`
   equals the MCP Resource_URL and whose authorization server is the lane pool.
3. WHEN the MCP to API grant is missing, THE MCP tool SHALL return an MCP URL
   elicitation error carrying the authorization URL. This is the only Phase 1
   onboarding mechanism for the direct path.
4. A connector that does not support URL elicitation SHALL be recorded as
   unsupported for this design. IF neither Claude nor Codex supports it, THEN
   Phase 1 SHALL be blocked until revised requirements are approved.
5. Authorization URLs SHALL NOT appear in tool result text that the model reads.
6. THE MCP Runtime SHALL expose `get_connection_status`, which reports whether
   the MCP to API grant is usable without calling the Sage API.
7. THE authorization server metadata that the protected-resource metadata
   points to SHALL be retrieved and checked by script. It SHALL include
   `issuer`, `authorization_endpoint`, `token_endpoint` and
   `code_challenge_methods_supported` containing `S256`.
8. IF `code_challenge_methods_supported` is absent or lacks `S256`, THEN THE
   Phase 1 gate SHALL record MCP authorization compliance as failed, the
   result SHALL NOT be described as MCP-compliant, and connector use beyond
   isolated testing SHALL require a recorded risk acceptance by the user.
   Observed on 8 October 2026, the Tenant_A Cognito OpenID discovery document
   omits this field and `/.well-known/oauth-authorization-server` is not
   served, so this criterion currently fails.

### Requirement 10: Agent path through a Gateway MCP-server target

**User Story:** As a web user, I want the agent to call Sage tools through the
Gateway with its own Gateway and MCP tokens, so that each hop is independently
authorized.

#### Acceptance Criteria

1. THE Gateway SHALL use an MCP-server target pointing at the lane MCP Runtime
   with an OAuth credential provider and the `AUTHORIZATION_CODE` grant.
2. THE target SHALL use DEFAULT listing with an explicit `mcpToolSchema`
   rendered from the MCP server's registered tools.
3. THE Gateway's outbound token SHALL carry `aud` equal to the MCP
   Resource_URL. IF spike S5 shows the Gateway cannot request it, THEN this
   design SHALL be blocked. Any alternative recipient-validation approach
   requires revised requirements and its own security assessment.
4. WHEN the Gateway returns a URL elicitation for a missing grant, THE Agent
   SHALL convert it into an `authorization_required` stream event and SHALL NOT
   pass it to the model.
5. THE Agent SHALL exclude `get_connection_status` from the model's tool list.

### Requirement 11: Independent Sage API validation

**User Story:** As the data owner, I want the Sage API to validate every token
itself, so that it remains the final authorization and isolation boundary.

#### Acceptance Criteria

1. THE Sage API SHALL verify signature, issuer, expiry, `aud` equal to the API
   Resource_URL, client equal to the lane MCP Outbound_Client, `token_use`
   equal to `access`, `sage-api/read` scope and the tenant claim.
2. THE Sage API SHALL keep its exact two-issuer allowlist and its tenant-scoped
   data reads unchanged.
3. THE Sage API SHALL reject Web_Client, Connector_Client and every other
   Outbound_Client token, including tokens from the same user and lane.

### Requirement 12: Credential safety

**User Story:** As a security reviewer, I want tokens, refresh tokens,
authorization codes and authorization URLs kept out of every unsafe sink.

#### Acceptance Criteria

1. Token values, refresh tokens, client secrets, session URIs and authorization
   URLs SHALL NOT appear in model input, tool result text, logs, traces, error
   bodies or persisted UI state.
2. Authorization URLs SHALL reach the user only through the Agent's
   `authorization_required` stream event, which the web app uses solely to
   navigate its popup, or through an MCP URL elicitation to the connector.
3. Logs SHALL record only correlation ID, lane, hop, stable outcome code and
   token `jti` where already permitted.
4. Outbound_Client secrets SHALL exist only in AgentCore Identity credential
   providers and SHALL NOT be written to manifests, outputs or the repository.

### Requirement 13: Tenant isolation

**User Story:** As a tenant data owner, I want every Tenant_A credential and
grant rejected by Tenant_B resources and the reverse.

#### Acceptance Criteria

1. EACH Door SHALL trust only its own lane's discovery URL and clients.
2. A token from either lane SHALL be rejected at every Door of the other lane.
3. Grants, credential providers, return URLs and workload identities SHALL be
   lane-specific, and no cross-lane completion SHALL succeed.

### Requirement 14: Route C replacement, cutover and rollback

**User Story:** As a platform operator, I want to replace Route C without
losing a working system during the change, so that a failed cutover can be
reversed.

#### Acceptance Criteria

1. New runtimes, Gateways, targets, clients, providers and the Sage API
   instance SHALL use names distinct from deployed Route C resources.
2. Route C-owned resources (its runtimes, Gateways, targets, Sage API instance
   and app clients) SHALL remain deployed and unmodified until both phases
   pass their verification gates.
3. Shared_Resources SHALL change only as listed in the design's shared-resource
   change table. EACH listed change SHALL have a recorded pre-change snapshot,
   a tested rollback step, and a Route C regression check run immediately
   before and after the change. A failed regression check SHALL trigger the
   rollback before any further step.
4. Phase 0 spikes SHALL NOT modify any Shared_Resource. They SHALL run in a
   scratch Cognito pool and scratch AgentCore resources.
5. Cutover SHALL be a frontend configuration change that is reversible by
   restoring the previous lane endpoints and client IDs.
6. AFTER cutover acceptance and explicit operator confirmation, THE operator
   SHALL delete Route C resources, and THE repository SHALL remove Route C-only
   code, configuration, tests and documentation in the same change.
7. THE steering files, README and the superseded `multi-tenant-agent-identity`
   spec SHALL describe the new credential model and SHALL no longer prohibit
   OAuth credential providers.
8. THE last Route C commit SHALL be tagged so its code can be redeployed.

### Requirement 15: Deployment safety

**User Story:** As a platform operator, I want every deploy step reviewable
and explicit, so that no cloud change happens by accident.

#### Acceptance Criteria

1. EVERY deploy script SHALL support a mutation-free `--render` mode and SHALL
   require `--confirm` before any AWS mutation.
2. Scripts SHALL read and write their configuration through the identity
   manifest and SHALL preserve the IPv4 endpoint workaround.
3. Cognito client updates SHALL use full read-modify-write and verify readback.

### Requirement 16: Verification gates

**User Story:** As the engineer advising Emil, I want recorded evidence for
each phase, so that the recommendation rests on observed behavior.

#### Acceptance Criteria

1. Phase 1 SHALL pass only when, for both lanes, a native Claude or Codex
   connector reads product and claim data after completing the MCP to API
   grant through URL elicitation alone, the MCP and API tokens differ, each
   carries its own `aud`, and the API rejects the MCP token and the MCP rejects
   the API token.
2. Phase 1 SHALL also record two OAuth security gates for each supported
   connector: the authorization server metadata check of Requirement 9.7, and
   public-client refresh token rotation of Requirement 2.7, shown by a refresh
   that returns a new refresh token and a reuse of the old one that fails after
   the grace period. A failed metadata check is handled by Requirement 9.8. A
   failed rotation check fails the gate.
3. Phase 2 SHALL pass only when, for both lanes, the web chat reads product and
   claim data after one Connect_Step, and a new browser session on a later day
   performs no Connect_Step redirects after the user signs in.
4. BOTH phases SHALL show rejection of cross-lane tokens, same-lane tokens for
   the wrong client, SDK tokens without `aud`, expired tokens, a revoked grant,
   an authorization completed by a different user, and a completion with a
   missing, expired, altered or other-user Pending_Transaction token.
5. EVERY Shared_Resource change SHALL show a passing Route C regression check
   before and after, or a completed rollback.
6. Evidence files SHALL contain only allowlisted claim names and outcomes.
