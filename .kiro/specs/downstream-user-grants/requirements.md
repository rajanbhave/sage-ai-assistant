# Requirements Document

## Introduction

This feature replaces Sage's JWT passthrough design (Route C) with on-behalf-of
(OBO) token exchange. It implements Option B, variant B1, from the comparison
in `docs/emil-authentication-options.md` and the design discussion of
8 to 9 October 2026.

Route C forwards the browser's Cognito access token unchanged through Agent,
Gateway, MCP and Sage API. The MCP authorization specification forbids an MCP
server from passing its received token to a downstream API, and
`mcp_server/sage_api_client.py` does exactly that today. This feature removes
that forwarding and the Gateway `JWT_PASSTHROUGH` target.

In B1 each lane gets its own Auth0 tenant. Auth0 is the badge office for every
hop. Users still sign in through the lane's Cognito pool, which still federates
to the customer's Okta or Entra, because Auth0 uses that Cognito pool as its
upstream identity provider. After sign-in, each workload asks AgentCore
Identity to exchange the token it received for a new token meant only for the
next hop. Auth0 performs the exchange. There is no consent popup and no stored
per-hop grant.

Two paths are in scope and are delivered in two phases:

```text
Phase 1  Claude/Codex -> MCP Runtime -> Sage API
Phase 2  Sage web app -> Agent Runtime -> Gateway -> MCP Runtime -> Sage API
```

AWS documents OBO token exchange as the pattern for "enterprise agents that
traverse multiple identity-aware services in a single trust domain". Cognito
cannot exchange tokens, which is why an exchange-capable issuer is added rather
than replacing Cognito.

Sage remains the proof of concept for Emil. Passing these gates validates the
pattern only. It does not authorize removing Emil's proxy, which still needs
Emil's API to accept the new access tokens and tests with real Okta or Entra
federation.

Platform behaviour this design relies on but that is not yet observed in Sage
(Auth0 claim handling across exchanges, AgentCore to Auth0 exchange parameters,
Gateway token exchange to a Runtime MCP target, connector OAuth against Auth0)
is treated as an unproven assumption until a Phase 0 spike passes. A spike
fallback that would change any requirement below is not a fallback. It blocks
the design until the requirements and security analysis are revised and
approved.

The superseded Option A spec (Cognito authorization-code grants with a
one-time Connect step) is kept in `archive/option-a/` as the fallback if Option
B is rejected.

## Scope Boundary

### In scope

- Exactly two lanes, Tenant_A and Tenant_B, each with its own Cognito pool,
  Auth0 tenant, Agent Runtime, Gateway, MCP Runtime and credential providers.
- An Auth0 OIDC enterprise connection from each lane's Auth0 tenant to that
  lane's Cognito pool.
- Auth0 APIs, applications, client grants and a post-login Action per lane.
- AgentCore Identity `CustomOauth2` credential providers using OBO token
  exchange for Agent to Gateway and MCP to Sage API.
- A Gateway MCP-server target using the `TOKEN_EXCHANGE` grant.
- Audience, client, scope, token type and tenant enforcement at every door.
- Web app sign-in through Auth0 with authorization code and PKCE.
- Cutover from Route C, a rollback path, and retirement of Route C code,
  configuration and documentation.

### Out of scope

- Option A authorization-code grants, consent popups, return pages and stored
  per-hop grants.
- Auth0 Custom Token Exchange (variant B2, where the app keeps Cognito tokens
  and the first hop swaps them).
- A shared Auth0 tenant, Auth0 Organizations, or a shared MCP serving several
  tenants. These form a separate "pooled" model, to be revisited only if the
  tenant count grows.
- Emil's API, Emil's proxy and real Okta or Entra federation.
- A third tenant, dynamic tenancy, write operations and new data tools.
- Machine-to-machine tokens reaching any Sage door, static tokens and shared
  service tokens.

## Glossary

- **Lane**: One of Tenant_A or Tenant_B and all resources bound to it.
- **Auth0_Tenant**: The Auth0 tenant dedicated to one lane. Its issuer URL is
  the lane's only trusted token issuer.
- **Upstream_Connection**: The Auth0 OIDC enterprise connection that signs
  users in through the lane's Cognito pool.
- **Hop**: One caller-to-receiver boundary. The hops are Web to Agent, Agent to
  Gateway, Gateway to MCP, Connector to MCP and MCP to API.
- **API_Identifier**: The Auth0 API identifier of a receiver. Auth0 places it
  in the access token `aud` claim. Each receiver has exactly one per lane.
- **Door**: A receiver that validates an inbound token. The doors are the Agent
  Runtime, Gateway and MCP Runtime managed authorizers and the Sage API code.
- **Web_Client**: The public Auth0 application used by the Sage browser app.
- **Connector_Client**: The public Auth0 application used by Claude and Codex.
- **OBO_Client**: A confidential Auth0 application that performs exchanges.
  Each lane has three: Agent, Gateway and MCP OBO clients.
- **Exchange**: One OBO token exchange at Auth0 that turns a token for one
  receiver into a token for the next, for the same user.
- **Principal**: The verified issuer and subject, plus the signed tenant claim
  `custom:tenant_id`.
- **Workload_Access_Token**: The AWS-signed opaque token AgentCore Runtime and
  Gateway deliver to a workload for calling AgentCore Identity.
- **Shared_Resource**: A resource used by both Route C and this design during
  migration: each lane's Cognito pool, its domain and its pre-token Lambda.

## Requirements

### Requirement 1: One exchange-capable issuer per lane

**User Story:** As a security reviewer, I want each lane to trust only its own
Auth0 tenant, so that tenant separation rests on separate issuers and signing
keys, as it does with separate Cognito pools today.

#### Acceptance Criteria

1. EACH lane SHALL have exactly one dedicated Auth0_Tenant, and no Auth0_Tenant
   SHALL serve more than one lane.
2. EACH Auth0_Tenant SHALL have exactly one enabled connection, the lane's
   Upstream_Connection. Database, social and passwordless connections SHALL be
   disabled.
3. THE Upstream_Connection SHALL use the authorization code flow with a
   confidential Cognito app client of the same lane, and SHALL be enabled only
   for that lane's Web_Client and Connector_Client.
4. Customer IdP federation into the Cognito pool SHALL remain unchanged.
5. EVERY Door SHALL trust only its own lane's Auth0 issuer and discovery URL.

### Requirement 2: Audience-bound token at every hop

**User Story:** As a security reviewer, I want each hop to receive a token
issued for that receiver only, so that a token replayed at another hop is
rejected.

#### Acceptance Criteria

1. EACH lane SHALL define exactly one Auth0 API per Door, with a distinct
   API_Identifier in absolute URI form. The eight identifiers across both lanes
   SHALL be distinct.
2. EVERY token presented to a Door SHALL have `aud` containing that Door's
   API_Identifier, and SHALL NOT contain another Door's API_Identifier.
3. EACH Door SHALL reject a token whose `aud` is absent or does not contain its
   own API_Identifier before any protected behaviour runs.
4. THE Auth0 APIs SHALL use the RFC 9068 access token profile, so that tokens
   carry `client_id` and the `typ` header `at+jwt`.
5. THE Auth0_Tenant SHALL enable the Resource Parameter Compatibility Profile,
   so that an RFC 8707 `resource` parameter selects the API.
6. THE MCP API_Identifier SHALL equal the `resource` value in the MCP Runtime's
   protected-resource metadata.

### Requirement 3: Least-privilege clients and exchange grants

**User Story:** As a tenant administrator, I want each client to obtain tokens
only for the one hop it serves.

#### Acceptance Criteria

1. EACH lane SHALL have exactly five Auth0 applications: Web_Client,
   Connector_Client and three OBO_Clients.
2. Web_Client SHALL be allowed only the Agent API. Connector_Client SHALL be
   allowed only the MCP API. The Agent OBO_Client SHALL exchange only for the
   Gateway API, the Gateway OBO_Client only for the MCP API and the MCP
   OBO_Client only for the Sage API.
3. EACH API SHALL define only its own scope: `sage-agent/invoke`,
   `sage-gateway/invoke`, `sage-mcp/invoke` and `sage-api/read`.
4. EACH Door SHALL accept only the client IDs assigned to it: Agent Runtime
   accepts Web_Client, Gateway accepts the Agent OBO_Client, MCP Runtime
   accepts the Gateway OBO_Client and Connector_Client, and Sage API accepts
   the MCP OBO_Client.
5. OBO_Clients SHALL be confidential first-party applications that
   authenticate with `PRIVATE_KEY_JWT`. Each SHALL have its own asymmetric KMS
   signing key, usable only through AgentCore Identity. Auth0 SHALL hold only
   the public key. IF spike S12 shows Private Key JWT cannot be used, THEN
   client secrets MAY be used, held only in Auth0 and in AgentCore Identity
   credential providers.
6. Web_Client and Connector_Client SHALL be public first-party applications
   requiring S256 PKCE, with refresh token rotation and reuse detection enabled.
7. Dynamic client registration SHALL be disabled unless spike S7 proves OBO
   works for a dynamically registered connector client and a revised
   requirement is approved.
8. Every API used in an Exchange SHALL allow skipping user consent, because no
   user is present during an Exchange.
9. EACH OBO_Client SHALL be an Auth0 Custom API client with `app_type`
   `resource_server`, `resource_server_identifier` equal to the API_Identifier
   of its incoming token (Agent OBO_Client: Agent API, Gateway OBO_Client:
   Gateway API, MCP OBO_Client: MCP API), and token exchange enabled for the
   `on_behalf_of_token_exchange` profile only.
10. EACH OBO_Client SHALL hold exactly one user-delegated client grant
    (`subject_type: user`), for the API named in Requirement 3.2 and that API's
    scope only.
11. EVERY Auth0 API SHALL set its user-delegated access policy to per-app
    authorization (`require_client_grant`) and its client access policy to
    `deny_all`. The only client grants in a lane SHALL be the five that
    Requirements 3.2 and 3.10 define.
12. AN Exchange presenting a token whose `aud` is not the OBO_Client's
    `resource_server_identifier`, or requesting an API the client has no grant
    for, SHALL fail.

### Requirement 4: Tenant claim and user identifier preserved in every token

**User Story:** As a tenant data owner, I want every Auth0 token to carry the
same signed tenant claim Cognito issues today, so that downstream tenant
authorization is unchanged.

#### Acceptance Criteria

1. THE Cognito `V2_0` pre-token customizer SHALL emit `custom:tenant_id` in the
   ID token issued to the lane's Upstream_Connection client.
2. THE Upstream_Connection SHALL map that verified claim onto an Auth0 user
   profile attribute that users cannot edit. Values from `user_metadata` SHALL
   NOT be used.
3. A post-login Action SHALL set the access token claim `custom:tenant_id` on
   every sign-in, refresh and Exchange in the lane.
4. THE Action SHALL deny the transaction IF the mapped value is missing,
   duplicated, or differs from the lane's configured tenant.
5. THE Action SHALL also set `cognito_sub` to the verified Cognito subject.
6. THE claim names and tenant values SHALL be configuration, unchanged from
   Route C.
7. EACH Door SHALL require `custom:tenant_id` equal to its lane tenant. IF
   Auth0 omits the claim (for example after a silent name collision), THEN the
   Door SHALL reject the token.
8. IF the exact claim `custom:tenant_id` cannot be issued unchanged at every
   hop, THEN this design SHALL be blocked. A different claim name requires a
   separately approved redesign and revised requirements.

### Requirement 5: No forwarding of a received token

**User Story:** As an MCP server operator, I want Sage to comply with the MCP
rule against token passthrough.

#### Acceptance Criteria

1. THE MCP application SHALL NOT send its inbound bearer to the Sage API.
2. THE Agent application SHALL NOT send its inbound bearer to the Gateway.
3. THE Gateway target SHALL NOT use `JWT_PASSTHROUGH`.
4. THE Agent and MCP applications SHALL use the inbound bearer only to read the
   Principal. The Exchange itself SHALL use the Workload_Access_Token.
5. A unit test SHALL fail if any outbound request from Agent or MCP code
   carries a bearer equal to the inbound bearer.

### Requirement 6: On-behalf-of exchange at each hop

**User Story:** As a Sage user, I want the agent and tools to act for me
without asking me to approve anything after sign-in.

#### Acceptance Criteria

1. THE Agent and MCP applications SHALL obtain downstream tokens through the
   AgentCore SDK `IdentityClient` (`GetResourceOauth2Token` with
   `oauth2Flow=ON_BEHALF_OF_TOKEN_EXCHANGE`), passing the platform
   Workload_Access_Token, the hop's credential provider, scope and
   API_Identifier. Application code SHALL NOT call the Auth0 token endpoint
   directly.
2. THE Gateway SHALL obtain its MCP token through an MCP-server target whose
   OAuth credential provider uses the `TOKEN_EXCHANGE` grant.
3. EACH credential provider SHALL be a `CustomOauth2` provider for the lane's
   Auth0_Tenant, configured with `onBehalfOfTokenExchangeConfig`, grant type
   `TOKEN_EXCHANGE` and the actor and subject token settings proven in S3.
4. THE credential provider name, scope and API_Identifier SHALL come from
   trusted deployment configuration and SHALL NOT be selectable by prompts,
   tool arguments, request headers or model output.
5. BEFORE using a downstream token, THE workload SHALL verify that its issuer,
   subject, tenant and `cognito_sub` equal the inbound Principal and that its
   `aud` contains the requested API_Identifier. IF any differ, THEN THE
   workload SHALL discard it and fail with a stable non-secret error.
6. AN Exchange failure SHALL fail the request with a stable code. No hop SHALL
   retry with a different credential or fall back to forwarding.
7. AFTER a user signs in, no hop SHALL show a consent, sign-in or approval
   screen.

### Requirement 7: Delegation chain visible to every receiver

**User Story:** As the data owner, I want the Sage API to know which service
called it and on behalf of which chain.

#### Acceptance Criteria

1. EVERY exchanged token SHALL carry an `act` claim naming the OBO_Client that
   requested it, nested over the earlier actors in the chain.
2. THE Sage API SHALL require the outermost `act.sub` to equal the lane's MCP
   OBO_Client and `client_id` to equal the same client.
3. THE Gateway and MCP doors SHALL accept tokens only from their assigned
   clients (Requirement 3.4). THE MCP application SHALL record whether the
   token arrived through the Gateway OBO_Client or the Connector_Client.
4. Logs SHALL record the `act` chain as client IDs only.

### Requirement 8: Sign-in, refresh and sign-out

**User Story:** As a Sage user, I want to sign in once and stay signed in for
the approved session length.

#### Acceptance Criteria

1. THE web app SHALL sign in through the lane's Auth0_Tenant with the
   authorization code grant, S256 PKCE, `state` and the Agent API_Identifier.
2. THE web app SHALL renew its token through Auth0 refresh token rotation in
   the browser. Renewal material SHALL never leave the browser.
3. Access token, refresh token and session lifetimes SHALL be approved
   deployment values recorded with their approval reference.
4. Sign-out SHALL revoke the web app's refresh token at the Auth0 revocation
   endpoint and end the Auth0 session. After sign-out, the old refresh token
   SHALL be rejected and silent sign-in SHALL require a new interactive
   sign-in. Because no per-hop grants are stored, the next sign-in SHALL NOT
   require any approval step.
5. Offboarding a user SHALL block the user in the lane's Auth0_Tenant, set
   `app_metadata.sage_access_revoked` (which the Action denies), and disable
   the user in the Cognito pool.
6. AFTER offboarding, every fresh Exchange, refresh and sign-in for the user
   SHALL fail immediately. Tokens already issued, including any exchanged token
   AgentCore Identity reuses within its lifetime, MAY remain usable until they
   expire. That residual access window SHALL NOT exceed the longest approved
   access token lifetime in the lane, recorded with its approval reference.

### Requirement 9: Direct Claude and Codex path

**User Story:** As a Claude or Codex user, I want to connect Sage's MCP server
with native OAuth and use it without the web app.

#### Acceptance Criteria

1. THE connector SHALL authenticate through the lane's Auth0_Tenant with the
   Connector_Client, S256 PKCE and `resource` equal to the MCP API_Identifier.
2. THE MCP Runtime SHALL advertise protected-resource metadata whose `resource`
   equals the MCP API_Identifier and whose authorization server is the lane's
   Auth0 issuer.
3. THE authorization server metadata SHALL be retrieved and checked by script.
   It SHALL include `issuer`, `authorization_endpoint`, `token_endpoint` and
   `code_challenge_methods_supported` containing `S256`.
4. THE MCP tools SHALL obtain the Sage API token by Exchange, exactly as on the
   Gateway path. No separate connector onboarding SHALL be needed.
5. Authorization server URLs and tokens SHALL NOT appear in tool result text.
6. A connector that cannot use a pre-registered client ID with Auth0 SHALL be
   recorded as unsupported. IF neither Claude nor Codex can, THEN Phase 1 SHALL
   be blocked until revised requirements are approved.

### Requirement 10: Agent path through a Gateway MCP-server target

**User Story:** As a web user, I want the agent to call Sage tools through the
Gateway with separately exchanged Gateway and MCP tokens.

#### Acceptance Criteria

1. THE Gateway SHALL use an MCP-server target pointing at the lane MCP Runtime
   with the Gateway OBO_Client credential provider and the `TOKEN_EXCHANGE`
   grant.
2. THE target SHALL use DYNAMIC listing, so that tool discovery also runs with
   an exchanged user token. No machine-to-machine token SHALL reach the MCP
   Runtime.
3. THE exchanged MCP token SHALL carry `aud` containing the MCP
   API_Identifier. IF spike S6 shows the Gateway cannot request it, THEN this
   design SHALL be blocked.
4. THE Agent SHALL forward no inbound credential to the Gateway and SHALL list
   tools with its exchanged Gateway token.

### Requirement 11: Independent Sage API validation

**User Story:** As the data owner, I want the Sage API to validate every token
itself, so that it remains the final authorization and isolation boundary.

#### Acceptance Criteria

1. THE Sage API SHALL verify signature against the issuer's published keys,
   issuer against an exact two-entry Auth0 allowlist, expiry, `typ` equal to
   `at+jwt`, `aud` containing the API API_Identifier, `client_id` equal to the
   lane MCP OBO_Client, the `act` chain of Requirement 7.2, the
   `sage-api/read` scope and the tenant claim.
2. THE selected issuer's lane tenant SHALL equal the token's `custom:tenant_id`.
3. THE Sage API SHALL keep its tenant-scoped data reads unchanged.
4. THE Sage API SHALL reject Web_Client, Connector_Client, Agent and Gateway
   OBO_Client tokens, Auth0 ID tokens and Cognito tokens, including tokens for
   the same user and lane.
5. THE Sage API SHALL fetch signing keys at run time from the `jwks_uri` of
   the configured issuer only, cache them for an approved bounded lifetime, and
   fail closed on an unknown key or an expired cache it cannot refresh. A key
   Auth0 adds SHALL be accepted without redeploying. A key Auth0 revokes SHALL
   stop being trusted within one cache lifetime.

### Requirement 12: Credential safety

**User Story:** As a security reviewer, I want tokens and secrets kept out of
every unsafe sink.

#### Acceptance Criteria

1. Token values, refresh tokens, client secrets and Auth0 management
   credentials SHALL NOT appear in model input, tool result text, logs, traces,
   error bodies, manifests, outputs or persisted UI state.
2. Logs SHALL record only correlation ID, lane, hop, stable outcome code, `act`
   chain client IDs and token `jti` where already permitted.
3. Auth0 management credentials used by deploy scripts SHALL be read at run
   time and held in memory only.

### Requirement 13: Tenant isolation

**User Story:** As a tenant data owner, I want every Tenant_A token rejected by
Tenant_B resources and the reverse.

#### Acceptance Criteria

1. A token from either lane SHALL be rejected at every Door of the other lane.
2. Auth0 tenants, connections, applications, credential providers and
   workload identities SHALL be lane-specific.
3. An Exchange presenting a token from another lane's Auth0_Tenant SHALL fail.

### Requirement 14: Exchange capacity

**User Story:** As a platform operator, I want Auth0 exchange limits sized
against real traffic before cutover.

#### Acceptance Criteria

1. Phase 0 SHALL measure Exchanges per chat turn and per direct tool call, and
   whether AgentCore Identity reuses an exchanged token within its lifetime.
2. THE design SHALL record the Auth0 plan, the Exchange rate limit that applies
   and the resulting maximum concurrent chat turns per lane.
3. AN Exchange rejected for rate limiting SHALL fail with a stable retryable
   code and SHALL NOT fall back to another credential.

### Requirement 15: Route C replacement, cutover and rollback

**User Story:** As a platform operator, I want to replace Route C without
losing a working system during the change.

#### Acceptance Criteria

1. New runtimes, Gateways, targets, credential providers, the Sage API instance
   and Cognito clients SHALL use names distinct from deployed Route C
   resources.
2. Route C-owned resources SHALL remain deployed and unmodified until both
   phases pass their verification gates.
3. Shared_Resources SHALL change only as listed in the design's shared-resource
   change table. EACH listed change SHALL have a recorded pre-change snapshot,
   a tested rollback step, and a Route C regression check run immediately
   before and after. A failed check SHALL trigger the rollback before any
   further step.
4. Phase 0 spikes SHALL NOT modify any Shared_Resource. They SHALL use a
   scratch Cognito pool, a scratch Auth0 tenant and scratch AgentCore
   resources.
5. Cutover SHALL be a frontend configuration change that is reversible by
   restoring the previous lane records.
6. AFTER cutover acceptance and explicit operator confirmation, THE operator
   SHALL delete Route C resources, and THE repository SHALL remove Route C-only
   code, configuration, tests and documentation in the same change.
7. THE steering files, README and the superseded `multi-tenant-agent-identity`
   spec SHALL describe the new credential model and SHALL no longer prohibit
   OBO, token exchange or OAuth credential providers.
8. THE last Route C commit SHALL be tagged so its code can be redeployed.

### Requirement 16: Deployment safety

**User Story:** As a platform operator, I want every deploy step reviewable and
explicit.

#### Acceptance Criteria

1. EVERY deploy script, including Auth0 configuration, SHALL support a
   mutation-free `--render` mode and SHALL require `--confirm` before any
   mutation.
2. Scripts SHALL read and write configuration through the identity manifest
   and SHALL preserve the IPv4 endpoint workaround.
3. Cognito and Auth0 updates SHALL use full read-modify-write and verify
   readback.

### Requirement 17: Verification gates

**User Story:** As the engineer advising Emil, I want recorded evidence for
each phase.

#### Acceptance Criteria

1. Phase 1 SHALL pass only when, for both lanes, a native Claude or Codex
   connector signs in through Auth0 and Cognito, reads product and claim data,
   the connector token and the API token differ, each carries only its own
   `aud`, the API token carries the tenant claim, `cognito_sub` and an `act`
   chain naming the MCP OBO_Client, and the API rejects the connector token.
2. Phase 1 SHALL record the authorization server metadata check (Requirement
   9.3) and public-client refresh token rotation (Requirement 3.6) for each
   supported connector.
3. Phase 2 SHALL pass only when, for both lanes, the web chat reads product and
   claim data with no screen after sign-in, and four distinct tokens are
   observed at the four doors.
4. BOTH phases SHALL show rejection of cross-lane tokens, same-lane tokens for
   the wrong client, Cognito tokens, Auth0 ID tokens, expired tokens, tokens
   without the tenant claim, Exchanges with the wrong incoming audience
   (Requirement 3.12), and a blocked user's next fresh Exchange, refresh and
   sign-in (Requirement 8.6).
5. EVERY Shared_Resource change SHALL show a passing Route C regression check
   before and after, or a completed rollback.
6. Evidence files SHALL contain only allowlisted claim names, client IDs and
   outcomes.
7. BOTH phases SHALL show two users of the same lane with different groups:
   the permitted user reads data, and the user without the API permission is
   refused at the MCP to API Exchange with `permission_denied`, with no call
   reaching the Sage API (Requirement 18).
8. Phase 2 SHALL show that after sign-out the old web refresh token is rejected
   (Requirement 8.4).
9. Phase 1 SHALL show that after an administrator removes a demo user's group
   in Cognito, the user's next interactive sign-in yields tokens without the
   removed scope, and the MCP to API Exchange is refused (Requirement 18.8).

### Requirement 18: Per-user permissions

**User Story:** As a tenant administrator, I want each user to receive only
the permissions assigned to them, so that belonging to a tenant does not grant
every permission in that tenant.

#### Acceptance Criteria

1. THE trusted permission source SHALL be the user's administratively assigned
   group membership in the lane's Cognito pool. Users SHALL NOT be able to
   change it.
2. THE Upstream_Connection SHALL carry `cognito:groups` from the verified
   Cognito ID token to an Auth0 profile attribute users cannot edit.
3. A lane permission map, deployed from the manifest, SHALL list for each
   group the scopes it may hold per API.
4. ON every sign-in, refresh and Exchange, THE post-login Action SHALL identify
   the target API, compute the union of scopes the user's groups allow for it,
   remove every other scope, and deny the request with `permission_denied` IF
   the target API's required scope is not allowed or the user is in no mapped
   group.
5. THE effective permission SHALL be the intersection of the application's
   client grant, the user's group permissions and the scope each receiver
   requires.
6. Auth0 RBAC (`enforce_policies`) SHALL NOT be enabled alongside Action scope
   changes, because Action scope changes override RBAC.
7. THE Upstream_Connection SHALL re-sync profile attributes, including
   `cognito:groups` and the tenant claim, on every interactive sign-in through
   Cognito.
8. Known POC limitation: a group or tenant change in Cognito SHALL take effect
   at the user's next interactive sign-in. Refreshes and Exchanges before that
   MAY continue to grant the previous permissions, because they do not
   contact Cognito. The Auth0 session and refresh token absolute lifetime SHALL
   be an approved ceiling of at most 12 hours, recorded with its approval
   reference, so that the maximum propagation delay for a removed permission
   is that ceiling plus the longest approved access token lifetime.
9. Production adoption SHALL replace the limitation in 18.8 with event-driven
   revocation (Cognito group, attribute and disable events revoking the user's
   Auth0 refresh tokens and sessions) before real users are onboarded. This is
   out of scope for the Sage POC and is recorded as an Emil handoff item.

