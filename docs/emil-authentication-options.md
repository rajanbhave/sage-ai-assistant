# Emil authentication: Cognito-compatible options

Status: research recommendation and test plan, updated 8 October 2026. Emil is the
customer system; Sage is the dummy proof of concept. The user validated the
problem statement before this comparison. No new authentication design has
been deployed by this investigation. The user requested comparison of both
options before choosing.

## Plan and task list

- [x] Verify current Cognito grant support and MCP July 2026 requirements.
- [x] Verify AgentCore Identity supports Cognito authorization-code grants.
- [x] Check Gateway target compatibility and trace Sage's current token flow.
- [x] Compare options for both Emil paths and identify required changes.
- [x] Run the current-config separate-grant test and record its limitations.
- [x] Consolidate the confirmed constraints, independent authentication
  problems, silent-authorization limits, research sources and current results.
- [ ] Prove resource audience binding in an isolated candidate.
- [ ] Implement and test the selected downstream authorization path in an
  isolated Sage candidate, preserving the existing deployment during the test.
- [ ] Verify real federated sign-in and Codex behavior before recommending a
  production cutover or removal of Emil's proxy.

Execution plan: first establish whether Cognito can issue separate grants with
the expected identity and destinations; then test direct MCP-to-API delegation;
then test the Agent/Gateway path, including session binding and tenant rejection.
Deploy infrastructure through IaC when the selected candidate is implemented.

## Validated problem

Each Emil tenant has an upstream IdP, such as Okta or Entra, federated into a
tenant Cognito pool. Cognito adds trusted tenant information. The customer
reports dedicated Agent Runtime, Gateway and MCP infrastructure per tenant;
the exact production deployment has not been inspected here. The required
paths are:

```text
Emil app -> Agent -> Gateway -> MCP -> Emil API
Claude/Codex -> MCP -> Emil API
```

Cognito issues ID and access tokens. Claude sends an access token; Emil's API
accepts ID tokens only. Adding tenant claims does not change the token type.
Yevgen's proxy reportedly works, but its actual credential handling remains to
be inspected. Retain that interim path until a replacement passes testing.

Cognito's token endpoint supports authorization-code, refresh-token and
client-credentials grants, not OBO/token exchange. AgentCore Identity can broker
an exchange only when the destination authorization server supports it.
[Cognito token endpoint](https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html)

The July 2026 MCP specification requires a token intended for the MCP resource
and prohibits forwarding its incoming client token to downstream APIs. It
describes a separate downstream access token. This is a credential-boundary
requirement, not a prohibition on JWTs.
[MCP security requirements](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations#access-token-privilege-restriction)

### Two independent problems

| Problem | What resolves it |
| --- | --- |
| Claude sends an access token; Emil's API accepts ID tokens | Add API access-token validation, or assess a separate legacy compatibility adapter. Custom tenant claims alone do not change token type. |
| MCP forwards its incoming bearer to the API | Replace that forwarding with a separately issued credential intended for the downstream API. This is required regardless of the API's current token-type support. |

The MCP rule is explicit: "The MCP server MUST NOT pass through the token it
received from the MCP client." It is a protocol requirement, not merely a
production preference. Accepting access tokens does not make passthrough
compliant. The mandatory change is a separate downstream credential; Option A
and Option B are different ways to obtain it. JWT formatting is not the
problem. This conclusion concerns the MCP-to-downstream boundary and is not a
blanket rule about every internal use of JWTs.

Keeping a proxy does not establish compliance either. Inspect its actual token
handling; placing the same forwarding behind another component does not fix
the credential boundary. Conversely, a separately issued downstream credential
is not passthrough merely because it represents the same user and tenant.

### Original call commitments and remaining coordination

The original commitments are taken from the user-provided, validated account
of the [1 October call](https://docs.google.com/document/d/1to7qchh_GRm2pIJRE-ZVYhs13DJJKkqBZLa-ydBmaI8).
No subsequent discussion with these people or AWS Support is evidenced here.

| Commitment | Recorded status |
| --- | --- |
| Investigate with Babatunde | Supported patterns researched; the discussion remains unconfirmed. Making an ID token "implicit" was an investigation, not an established capability. |
| Reproduce with Sage MCP and Claude Desktop | Sage functional path and user-reported native Claude calls succeeded. Full separate-token compliance and real Emil federation remain unproven. |
| Correct the Lite guidance | Ordinary Lite supports ID-token customization through V1_0; Essentials/Plus support user access-token customization through V2_0. AWS also documents a grandfathered Lite exception for qualifying legacy advanced-security pools; do not generalize it to all Lite pools. |
| Seek AWS guidance if needed | Public AWS documentation and reference designs reviewed and linked below. An Emil-specific AWS support/architecture review has not been completed. |
| Yevgen to discuss API access-token support with Hussein | Parallel customer action; its outcome remains unknown. |

[Cognito tier and trigger documentation](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-token-generation.html)

## Current recommendation under Emil's confirmed constraints

The customer-managed upstream IdPs cannot be changed to add Emil's claims.
Changing Emil's existing tenant representation and API tenant logic is also
infeasible. Retain Cognito federation and preserve the existing tenant claim
names, values and business meaning.

Option A is the recommended first candidate under these constraints, provided
Emil can add access-token validation at its authentication boundary. This is an
engineering recommendation based on AWS's documented Cognito authorization-code
integration, not an AWS endorsement of Emil's untested architecture. Keep the
legacy ID-token validator during migration, normalize validated identities into
the same internal principal, and preserve downstream tenant/business checks.
Whether this is a small centralized change or affects many APIs must be
established from Emil's implementation; do not assume every API shares one
validator.
[AWS Cognito integration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-idp-cognito.html#outbound)

Execution plan and outstanding checks:

- [x] Reconcile the recommendation with the customer-IdP and tenant-model
  constraints; no new design is treated as approved for deployment.
- [ ] Inventory the exact custom claim schema and prove identical tenant
  interpretation in ID and access tokens.
- [ ] Locate Emil's token-validation boundary and determine whether additive
  access-token support is feasible without tenant/business logic changes.
- [ ] Prove separate resource audiences, per-user token storage, onboarding,
  refresh and both application paths in an isolated candidate.

Configure the Cognito pre-token Lambda to issue the required custom tenant
claims in access tokens using V2_0 on Essentials/Plus. AgentCore Identity stores
and refreshes each separately authorized downstream grant. Browser session
reuse can reduce credential prompts; it does not provide server-side OBO.
[Cognito customization](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-token-generation.html),
[Cognito silent authorization](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html)

If seamless delegation with no additional downstream authorization flow is a
hard requirement, Option B remains a candidate, but introduces another issuer
and corresponding API trust changes. Preserving custom claim names in its
tokens does not make them Cognito tokens or eliminate API validation changes.

If APIs must remain strictly Cognito-ID-token-only with no authentication
changes, neither A nor B is a drop-in replacement. Retain the reported proxy
as an interim path and inspect its credential issuance, user/session binding,
tenant checks and downstream behavior before claiming security or compliance.
Do not describe it as an automatic access-to-ID-token conversion: Cognito does
not expose that exchange grant. A separately issued legacy credential would
still be an adapter strategy, not the recommended OAuth API access-token path.

## Option A: Cognito authorization code and managed per-user token storage

Recommended first candidate when additional authorization during onboarding is
acceptable. Retain each tenant's Cognito federation and obtain a separate user
grant for each downstream resource. AgentCore Identity stores and refreshes the
downstream tokens. This does not exchange the incoming token, and it does not
require Cognito to support OBO.

AWS documents Cognito as an outbound provider using a confidential app client,
authorization-code grant, and the provider-specific callback. AgentCore
Identity supports refresh-token storage and resource indicators.
[Cognito outbound provider](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-idp-cognito.html#outbound),
[Token retrieval and refresh](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-authentication.html)

### Application path

| Boundary | Credential used | Where it comes from |
| --- | --- | --- |
| App -> Agent | User access token intended for Agent | App's normal Cognito authorization |
| Agent -> Gateway | Separate user access token intended for Gateway | Separate Cognito grant, retrieved by the Agent for the authenticated user |
| Gateway -> MCP | Separate user access token intended for MCP | Gateway's authorization-code credential provider |
| MCP -> API | Separate user access token intended for API | MCP's authorization-code credential provider |

The grants can be completed during onboarding and reused until they expire or
are revoked. Reauthorization remains necessary when the stored authorization
is no longer usable. Existing browser SSO may reduce repeated credential entry;
it is not a guarantee of zero prompts.

### When Alice needs to authorize

Grants can be requested on first use rather than generated for every possible
service in advance. Stored grants are reused and refreshed for subsequent
calls; each hop does not ask Alice to sign in for every invocation. If a needed
grant is missing or unusable, the application must arrange its authorization
flow. For direct Claude/Codex access, the MCP needs a downstream connection or
onboarding flow; connector login alone does not authorize the API.

Cognito Managed Login supports `prompt=none` for an existing browser session
across app clients in the same user pool. Classic Hosted UI does not support
that parameter. Without a valid session it returns `login_required`, requiring
a normal sign-in fallback. Requests still need browser redirects and callbacks;
this is silent authorization using code + PKCE, not the OAuth implicit grant.
`prompt=none` is not forwarded to upstream IdPs. An app login performed only
through an SDK, or a session only at Okta/Entra, is not automatically a Cognito
browser session. Separate pools do not share that session.
[Silent authorization](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html)

Cognito's browser cookie lasts one hour; separate refresh tokens can renew
existing grants without the browser. Backend services cannot use Alice's cookie
or turn an incoming access token into arbitrary destination tokens. Native OBO
remains unavailable in Cognito.
[Managed Login session](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html),
[Refresh grants](https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html)

Gateway supports authorization-code outbound access for an MCP-server target.
The current Sage target is `http.passthrough`; do not assume changing its grant
setting is sufficient. Create an isolated MCP-server target candidate and
verify the supported protocol, indexing, resource parameter and consent flow.
AWS documents that DYNAMIC listing is not compatible with outbound 3LO; use
DEFAULT with authorized discovery or an explicit tool schema.
[Gateway MCP targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html)

### Direct client path

Claude/Codex obtains the MCP token through native OAuth and Cognito federation.
The MCP separately obtains an API token using AgentCore Identity. The client
never supplies the API bearer as a second header or tool argument.

The downstream grant needs its own onboarding/callback experience. A managed
Gateway consent portal is attached to a Gateway; it is not automatically a
consent portal for a direct MCP Runtime connection. Test a dedicated application
callback/session-binding flow for direct MCP, or pre-authorize access through
Emil's application. Test client support before relying on MCP elicitation.
[Managed consent portal](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-consent-portal.html),
[Gateway session binding](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html)

### Identity and authorization rules

- Select tenant configuration from validated identity and a trusted issuer-to-
  tenant mapping. Reject disagreement with the signed tenant claim. Do not use
  an unverified tenant header or tool argument to select a credential provider.
- Use the verified issuer and subject together as the user key; subjects are
  not globally unique across pools. Bind token storage to that user, tenant,
  workload and resource/provider.
- Validate downstream Cognito issuer, subject and tenant against the initiating
  identity. Session binding prevents flow theft; it does not justify allowing
  an unrelated downstream account for Emil's same-user requirement.
- Each receiving service verifies signature, expiry, token type, approved client,
  its intended resource and operation-specific permissions. Both scope and user
  entitlements matter.
- Request one resource per grant and enforce the resulting `aud`. Cognito
  preserves that resource on refresh; refreshing an MCP token does not turn it
  into an API token. Verify resource binding on the actual hosted-login setup.
  SDK password/SRP sign-in does not provide this resource binding.
  [Cognito resource binding](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html)
- Keep credentials out of prompts, tool arguments and logs. Record allowlisted
  identity and validation outcomes only.

### Changes required

1. Emil API adds access-token support with a separate validator; retain the
   legacy ID-token path during migration. Normalize both into its internal
   principal and apply the same tenant/business authorization rules.
2. Add destination-specific resource identifiers and scope grants to the
   tenant Cognito setup. Use separate public external-client and confidential
   server-side clients where appropriate; a new client alone is not audience
   binding. Preserve existing client configuration.
3. Customize access tokens with trusted tenant context through the supported
   trigger. Sage's current trigger adds all four scopes to every approved grant;
   limit new candidate clients to their intended scopes while preserving the
   existing deployment during testing.
4. Configure credential providers, workload permissions and callbacks, and
   implement consent/session binding. Replace incoming-bearer forwarding in
   Agent/MCP clients with retrieval of the correct downstream credential.
5. Enforce resource audiences at the managed doors and API, and test discovery,
   PKCE metadata, callbacks and refresh behavior against actual clients.

This option can remove a dedicated token-conversion proxy if all tests pass.
It still adds managed token storage and onboarding responsibilities. Native
end-to-end behavior has not yet been proven in Sage.

## Option B: Exchange-capable authorization service

Recommended candidate when seamless delegation after the initial user login
is mandatory. Keep Cognito for federation, but introduce an authorization
service that explicitly trusts the relevant Cognito issuers and supports
exchange. It validates the incoming token, user/tenant mapping and actor
permission, then issues a destination-specific token with no escalation of
user permissions. Every receiver trusts the new issuer and validates its own
audience.

AgentCore Identity brokers the supported grant. Gateway exchanges for MCP;
MCP exchanges for API. An Agent can obtain a Gateway token in the same way.
For a direct client, Cognito can remain the MCP issuer; MCP exchanges that
token at the trusted service for an API token. If a broker instead becomes the
external MCP issuer, it must also supply native OAuth discovery and login.
Neither configuration is implicit or supplied by Cognito itself.
[AgentCore OBO](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)

Do not assume a customer's original Entra or Okta endpoint will exchange a
Cognito-issued token. Compatible cross-issuer trust and claim mapping must be
configured and tested. User identifiers may need explicit mapping across
issuers; preserving the literal `sub` string is not a universal guarantee.

Once the necessary trust and authorization are established, this avoids new
downstream connection flows when policy permits the exchange. It does not
bypass initial consent, administrative permissions or authentication challenges.
It introduces an authorization service, trust policies and token-issuance
operations. It can replace the existing proxy's role; it does not promise fewer
components.

## Alternatives that change the requirements

Tenant-specific service credentials can be suitable when operations are
authorized as the tenant service. They do not preserve individual user
authorization. A shared service token plus a claimed user/tenant header is not
a replacement for the validated requirement. A deliberately trusted service
authorization design is possible only if Emil explicitly accepts that trust
model and its enforcement responsibilities.

## Current-config Sage result

The user reported successful native Claude connector calls for AXA product and
claim tools, including AXA Drive Protect (AXA-MOT-001). Separate scripted checks
passed direct access-token calls, denied ID and wrong-tenant tokens, and verified
Gateway/Agent behavior after the correlation-header fix. This establishes
functional Sage access-token compatibility, not Emil API compatibility.
See [Claude setup and test](claude-desktop-test.md) and the dated
[scripted verification snapshot](claude-mcp-correlation-after.json). The snapshot
predates the user's successful retry; its pending-native-Claude field is
historical, not the current conversational status. Exact Claude version and
a dedicated allowlisted capture of the native OAuth exchange remain unrecorded.

Sage still forwards its received bearer in
[`SageApiClient._get`](../mcp_server/sage_api_client.py), and its current Gateway
target uses JWT_PASSTHROUGH. Neither functional success nor preserved tenant
claims proves the new design. The proposed separate downstream credentials
have not been implemented. Discovery/PKCE metadata also remains a compliance
test item even though the observed sign-in worked.

Two real authorization-code grants were completed on 7 October 2026 using the
same Tenant_A local demo user, requesting the MCP and API resources separately.
Access-token signatures, issuer, expiry, token type and client binding were
verified. The two access-token values differed; issuer, subject and tenant
matched. Each response included an ID token and a refresh token.

Neither access token included `aud`, and both carried all four Sage scopes.
The resource parameter was preserved on the public login redirect and forms.
AWS MCP readback confirmed the domain is ACTIVE with ManagedLoginVersion 1
(classic hosted UI). AWS documents resource binding for Managed Login in
Essentials/Plus. The current test therefore fails the audience-binding
acceptance check; it is not proof of the complete Option A design. The exact
causal fix still needs a managed-login candidate test, and changes to scope
customization are independently required for least privilege.

Evidence: [cognito-separate-grants-evidence.json](cognito-separate-grants-evidence.json).
No infrastructure was changed. No credentials or token values were recorded.
[Resource-indicator availability](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-cognito-resource-indicators-protection-oauth-2-0-resources/)

## Sage validation sequence

1. Without changing deployment, issue two Cognito authorization-code grants for
   the same test user with different resources. Confirm distinct token values,
   matching verified issuer/subject/tenant, expected audiences and token types.
   Store only redacted evidence. This is a local-user test, not proof of federated
   Okta/Entra behavior or downstream token-vault integration.
2. Deploy an isolated MCP/API candidate through IaC. Keep current endpoints and
   tenants available. Add a dedicated API credential provider and implement its
   bound onboarding flow.
3. Prove Claude -> MCP -> API uses separate tokens; API rejects the MCP token,
   and MCP rejects the API token. Test cross-tenant and same-tenant other-user
   substitution, missing consent, expiry, refresh, revocation and malformed
   credentials. Verify user permissions as well as tenant isolation.
4. Add the Agent/Gateway candidate with supported MCP-server target and 3LO.
   Complete the exact callback/session-binding flow, then repeat both tenant
   reads and user-permission rejection. Verify normal calls reuse stored grants.
5. Repeat with actual federated users and Codex. Check native discovery and
   selected protocol version, including PKCE metadata. Preserve original
   password/SRP/refresh behavior until the application migration is accepted.
6. Inspect Yevgen's actual proxy and Emil's API validation before removing it.
   Record the residual components, rollback path and production changes.

### Completion and proxy-removal criteria

Give Emil a tested recommendation only after both paths pass with actual
federated users: correctly bound resource tokens, preserved custom tenant
schema and user permissions, distinct downstream credentials, rejection of
wrong-resource/wrong-tenant/wrong-user requests, grant reuse and refresh, and
verified Claude/Codex OAuth discovery. The existing application path needs a
regression check and a rollback plan. Document the required API/Cognito changes
and remaining operational components. Remove the proxy only after its role is
understood and the replacement passes these checks; successful Sage calls alone
do not meet the completion criteria.

## Recommendation and current boundary

Under the now-confirmed customer-IdP and tenant-model constraints, Option A is
the first candidate if additive API access-token validation is feasible.
Option B is the stronger fit when eliminating downstream browser flows is a
hard requirement, but requires another issuer and API trust changes. If all
API authentication changes are excluded, keep the interim adapter and inspect
it rather than claiming either option is deployable. The user has requested
comparison before choosing; no implementation choice is treated as approved.
Do not build a custom exchange endpoint solely to demonstrate a feature Cognito
does not offer. None of these candidates is yet a tested production recommendation.

## Published implementation research, 8 October 2026

Research tasks: compare AWS guidance, named customer implementations and vendor
patterns; distinguish architectural fit from deployment evidence; verify the
Cognito constraint. Research completed without changing infrastructure.

AWS's authentication-pattern guide distinguishes authorization-code grants for
separately authorized user services from OBO for already-authenticated users
traversing identity-aware services in one trust domain. It supports mixtures of
patterns, rather than mandating one for every integration.
[AWS pattern selection](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/common-use-cases.html)

AWS published a multi-tenant OBO reference implementation on 13 July 2026 using
Okta custom authorization servers, destination audiences and tenant/user data
isolation. This is a reference implementation, not evidence that Emil's
Cognito federation can perform the exchange. AgentCore Identity brokers a
request to an exchange-capable authorization server; Cognito's documented
token grants remain authorization code, refresh token and client credentials.
[AWS multi-tenant OBO reference](https://aws.amazon.com/blogs/machine-learning/implement-on-behalf-of-token-exchange-for-multi-tenant-agents-with-amazon-bedrock-agentcore-gateway/),
[AgentCore exchange mechanism](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html),
[Cognito grants](https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html)

| Published example | Observed pattern and evidence boundary |
| --- | --- |
| Microsoft Azure MCP Server | Option B pattern: exchanges the user's token for downstream Azure tokens, retaining user permissions. This is a documented deployment template using Entra, not an automatic bridge from Cognito. [Microsoft guide](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/how-to/deploy-remote-mcp-server-on-behalf-of) |
| WisdomAI using Descope | Named customer case: enterprise SSO, customer-facing MCP authorization and a vault for stored/refreshed external-service credentials. The outbound vault is an Option A-style pattern; the case also mentions exchange, so it does not establish exclusive A or B adoption. [Customer case](https://www.descope.com/customers/wisdomai) |
| Auth0 Token Vault | Option A-style product pattern: connect an external service, retain its refresh token, obtain access tokens later. Token-retrieval terminology does not prove the downstream provider implements OBO. [Auth0 walkthrough](https://auth0.com/blog/connect-oauth2-service-to-ai-agents-with-auth0-token-vault/) |
| Descope internal resources | Option B product pattern: exchange an inbound token for a different resource's token; external services instead use stored connection credentials. This documents support for both, not customer adoption rates. [Downstream patterns](https://docs.descope.com/agentic-identity-hub/auth-patterns/downstream-credential-access) |
| ORIX PATPOST with AWS | Named customer PoC, published 1 October 2026: Cognito authenticates the MCP caller; a Gateway interceptor retrieves that user's API key from RDS for the backend. Neither exact A nor B. The backend already accepts per-user API keys, unlike Emil's stated ID-token-only API. [AWS customer case, Japanese](https://aws.amazon.com/jp/blogs/news/agentcore-gateway-patpost/) |

No inspected source establishes that most organizations with Emil's exact
per-tenant Cognito and ID-token-only API setup choose A or B. The evidence
supports exchange for internal delegation and stored grants for separately
authorized external integrations; companies can combine them.

An exchange-capable managed issuer can potentially trust Emil's Cognito pools,
validate their identity and tenant claims, and issue API-specific access
tokens. Auth0 Custom Token Exchange explicitly supports external identity
providers with custom validation. This is a candidate requiring policy,
protocol and tenant-isolation testing, not a preconfigured Cognito integration.
[Custom Token Exchange](https://auth0.com/docs/authenticate/custom-token-exchange)

For either token-based option, Emil's API must accept the correctly issued
access token and retain its tenant/business permission checks. Neither OAuth
pattern automatically fixes an ID-token-only validator. Keep the existing
proxy until the chosen replacement passes both paths and federated-user tests.

## Option B variant: use the tenant's original IdP directly

Confirmed customer constraint, 8 October 2026: the upstream IdPs are managed by
Emil's customers, and changing their custom claims is not available. Exclude
that dependency from the proposed solution. Whether customers can configure
OAuth applications, delegated permissions and OBO remains a separate open
question; existing federation does not prove those capabilities are enabled.

Research update, 8 October 2026. Given Emil's stated dedicated Runtime, Gateway
and MCP per tenant, direct Okta/Entra authentication is a conditional candidate. It
can use the tenant's existing exchange-capable authorization server instead of
introducing another issuer. Dedicated infrastructure simplifies trusted tenant
configuration; it does not by itself authorize every user in that directory.

Plan and task list:

- [x] Confirm native Okta/Entra delegation and claim customization mechanisms.
- [x] Describe both paths and alternatives to the Cognito tenant claim.
- [x] Incorporate the constraint that customer IdP custom claims cannot change.
- [ ] Inventory Emil's actual Lambda-added claims and their authoritative data
  sources; distinguish fixed tenant configuration from per-user entitlements.
- [ ] Confirm customer IdP capabilities, administrator cooperation and licensing.
- [ ] Test native connector OAuth, each audience, exchange and user/tenant
  identity mapping in an isolated candidate before changing existing routes.

### Both paths

| Path | Candidate flow |
| --- | --- |
| Emil app -> Agent -> Gateway -> MCP -> API | The app gets an original-IdP token for the Agent; Agent obtains a Gateway token; Gateway obtains an MCP token; MCP obtains an API token. Configure each exchange and destination's validation explicitly. |
| Claude/Codex -> MCP -> API | The connector authenticates against the tenant's original IdP for the MCP resource. MCP obtains an API-specific token through OBO. The API validates the original IdP's access token and applies Emil's business authorization. |

AgentCore Identity can broker these exchanges; the customer's IdP issues the
tokens. Initial user/admin authorization and conditional-access policies still
apply. Native OAuth discovery, resource/audience behavior and client registration
must be tested with Claude and Codex; the customer's existing SAML SSO setup
alone is not an OAuth/OBO configuration.
[AgentCore OBO](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)

Entra requires delegated permissions and a middle-tier-specific inbound
audience. Register each middle tier appropriately and use its corresponding
credential provider. Custom signing keys on a middle-tier application are
incompatible with its documented OBO flow. Okta documents exchange within a
custom authorization server or between trusted custom servers in one Okta org.
Do not assume these native flows exchange existing Cognito tokens.
[Entra OBO](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow),
[Okta OBO](https://developer.okta.com/docs/guides/set-up-token-exchange/main/)

### What happens to the Cognito Lambda's claims?

The alternatives in this subsection are retained to explain the research.
Moving tenant context into deployment configuration or a new authorization
lookup is outside Emil's confirmed current constraints because it requires
unacceptable API tenant-model rework. Original-IdP claim changes are also
excluded. These alternatives are not the current implementation recommendation.

They are not copied automatically: bypassing Cognito means its pre-token
Lambda does not run. Identity and tenant context can nevertheless be preserved
without reproducing every field inside the JWT. The following are design
alternatives, not confirmed details of Emil's current implementation.

1. **Fixed tenant context from trusted deployment configuration.** Tenant A's
   services know their Emil tenant ID. They accept only the configured IdP
   issuer/directory and the correct destination audience, then check that the
   authenticated user is entitled to that Emil tenant. The API derives tenant
   context independently from validated identity and its trusted mapping or
   dedicated deployment. An unverified header, requested URL or user-supplied
   tool argument is not proof of membership. Entra's `tid` is its directory ID,
   not automatically Emil's business tenant ID. One directory can serve more
   than one Emil tenant, requiring explicit membership/resource mapping.
2. **Original-IdP custom claims: excluded for Emil.** The providers have claim
   customization features, but Emil cannot change its customers' claim
   configuration. Preserve the references as research evidence, not as an
   implementation option. OBO does not automatically recreate Cognito fields.
   [Okta claims](https://developer.okta.com/docs/guides/customize-tokens-returned-from-okta/main/),
   [Entra optional claims](https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims)
3. **Emil-owned authorization lookup.** After validation, map the IdP user to
   Emil's internal user, roles and entitlements in trusted application data.
   This preserves business rules that belong to Emil and avoids requiring the
   customer to manage those values in its IdP. If a signed Emil-specific token
   is required instead, an Emil-trusted issuer/broker remains necessary.

Do not rewrite an Okta/Entra JWT to add fields: that invalidates its signature.
Keep derived context in the server's internal principal. If downstream APIs
require these values inside a signed token, an Emil-controlled trusted issuer
must issue that token; do not depend on modifying the customer's issuer.

Migration also changes the source of user identifiers. Map existing Cognito
users to stable upstream identities; do not use email or assume `sub` stays
identical across issuers or resources. For Entra, use validated directory/user
identifiers (`tid`, `oid`) for cross-service correlation where applicable;
`sub` is application-specific.
[Entra identity claims](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference)

### Decision boundary

Direct IdP remains a candidate if OBO can be configured and Emil's services can
derive the fixed tenant and user permissions from their own trusted data. It
does not require custom claims in that case. Dedicated infrastructure alone
does not remove the required IdP application/permission configuration.

If the API requires Emil-specific claims inside the signed bearer, retain
Cognito with separate grants (Option A), or retain Cognito's existing
federation and use an Emil-controlled exchange-capable issuer (Option B).
The latter validates the Cognito token, restricts the user/tenant/actor grant,
and issues a destination-specific access token containing trusted Emil claims.
It does not rely on customer IdP claim changes, but introduces issuer trust and
operations. AgentCore Identity brokers the exchange; it does not supply the
new issuer. The plain direct-IdP route is not the unconditional recommendation
under this constraint.

Emil's API still needs an access-token validator for the selected upstream
issuers, destination audience, delegated permissions and trusted tenant/user
mapping. Introduce this alongside the legacy Cognito path and test both
applications before retirement. Neither Cognito nor the proxy can be declared
removable until these requirements pass against real tenant IdPs.
