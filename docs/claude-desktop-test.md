# Sage MCP with Claude Desktop

Use Claude's native remote connector to test its OAuth behavior. A manually
supplied bearer or a local MCP bridge does not test which token Claude selects
from Cognito's OAuth response.

## Plan and task list

- [x] Trace Sage's MCP, Cognito customizer, authorizers, and Sage API validation.
- [x] Check public OAuth discovery and the unauthenticated MCP challenge.
- [x] Restore AWS SSO access.
- [x] Read the deployed pool domain, app-client OAuth settings, trigger, and
  Gateway target configuration without outputting secrets.
- [x] Render and review the necessary Cognito changes, then apply them.
- [x] Add the native remote connector in Claude Desktop and sign in, confirmed
  by the user's successful tool-call report.
- [x] Invoke product and claim tools for AXA through the native connector,
  confirmed by the user.
- [ ] Record the exact Claude version and a dedicated allowlisted native OAuth
  token-type capture; scripted access/ID-token behavior is already verified.

Start with Tenant_A. Reuse its existing public app client if compatible: the
customizer, managed authorizers, and Sage API already trust that client. Adding
a different client requires updating all those trust bindings and its subject
scope grant. Preserve existing client settings when configuring OAuth.

Execution plan approved by the user: save the existing public client settings;
test password login, refresh, and the existing Sage path; create Tenant_A's
hosted-login domain and custom scopes through CloudFormation; enable code-flow
OAuth on the existing client with a full read-modify-write; repeat the existing
path checks; then connect Claude directly to the MCP Runtime and test OAuth.
Only Tenant_A is changed. Its MCP runtime was updated to version 2 for optional
correlation headers. No Gateway or Agent deployment is part of this setup.

## Verified on 7 October 2026

Tenant_A connection details from repository deployment configuration:

| Setting | Value |
| --- | --- |
| Connector name | Sage MCP - AXA |
| Direct MCP URL | `https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A434801484416%3Aruntime%2Fsage_mcp_tenant_a-eSX4mQEcRb/invocations?qualifier=DEFAULT` |
| Target-specific MCP URL | `https://sage-gw-tenant-a-d3xlgrubpv.gateway.bedrock-agentcore.us-east-1.amazonaws.com/sage-mcp-tenant-a/invocations` |
| Cognito pool | `us-east-1_72f3bUHBE` |
| Existing public client ID | `7gl3vm6r1kjmu8bb1o4o3279tn` |
| Tenant login username | `axa-user` |
| Claude callback | `https://claude.ai/api/mcp/auth_callback` |

Live unauthenticated checks:

- The target-specific MCP URL returns HTTP 401 and a `WWW-Authenticate` header
  pointing to the Gateway's `/.well-known/oauth-protected-resource` metadata.
- That metadata returns HTTP 200, points to the Tenant_A Cognito issuer, and
  advertises `sage-gateway/invoke`.
- The metadata's `resource` is the Gateway's `/mcp` URL, rather than the
  target-specific URL. `/mcp` also returns a 401 challenge. Authenticated checks
  must establish which URL exposes the intended tools. The Claude test now uses
  the direct MCP Runtime URL, whose live metadata matches that URL exactly.
- Cognito discovery now points authorization/token endpoints to the configured
  hosted-login domain. It does not advertise DCR, CIMD, or S256 PKCE; the actual
  hosted sign-in page accepts the exact Claude callback and S256 PKCE.
- After SSO renewal, the live Tenant_A pool is `ESSENTIALS` and its trigger is
  `V2_0`, bound to `sage-pre-token-tenant-a:tenant-a`.
- CloudFormation stack `sage-claude-oauth-tenant-a` created the hosted-login
  domain `sage-claude-tenant-a-434801484416` and four resource-server scopes.
- The existing public client now permits authorization code OAuth, `openid`,
  all four Sage scopes, and the exact Claude callback. All previous client
  settings were preserved and verified by readback.
- Password, SRP, refresh, Gateway tools, Agent responses, direct access-token
  acceptance and ID-token rejection passed after configuring OAuth.
- Claude rejects the unapproved custom header `X-Sage-Correlation-Id`. Remove
  it from the connector. The MCP fix generates an ID only when absent, preserves
  supplied IDs and rejects malformed or duplicate values.

The repository API already requires `token_use=access`, trusted issuer/client,
`sage-api/read`, and a valid tenant claim. Its V2 customizer populates both ID
and access token tenant claims. This makes Sage a candidate demonstration of an
API accepting access tokens; it does not establish compatibility with Emil's API.

## Connector setup

1. Completed: configure a Cognito hosted-login domain and authorization code grant with
   S256 PKCE for the public client. Register the exact Claude callback above.
   Keep the client secret absent and preserve existing frontend sign-in flows.
2. Check available resource-server scopes and the customizer's approved subject
   grant. The complete Gateway-to-API path requires `sage-gateway/invoke`,
   `sage-mcp/invoke`, and `sage-api/read`. Request `openid` to test a response
   containing both ID and access tokens. Confirm the actual resulting claims;
   requested scopes alone do not establish authorization.
3. In Claude Desktop, open Customize > Connectors > Add custom connector.
   Enter the direct MCP Runtime URL above. Choose sign-in and "Use your own OAuth client"
   if offered; enter the existing public client ID and leave the secret blank.
   Cognito discovery does not advertise dynamic registration, so do not select
   automatic registration. If the account lacks custom-client entry, record that
   limitation before choosing another integration path.
4. Resolve discovery/resource URL compatibility using the live authenticated
   result. Do not introduce a token-conversion proxy to conceal onboarding errors.
5. Leave Request headers empty. Tenant_A MCP generates a correlation ID when
   the client omits it; existing Gateway callers can continue supplying one.

## Test and evidence

After signing in, enable the connector in a new conversation and ask:

> Use Sage MCP to get motor product information, then get claim CLM-12345.

Capture:

- Claude client/version and connector mechanism; Cognito tier and trigger version.
- Successful login and discovery of `get_product_info` and `get_claim_details`.
- A successful Tenant_A result and correlation ID.
- OAuth response field names confirming both token types were issued, and only
  safe allowlisted claim evidence at the receiving boundary confirming
  `token_use=access`, expected issuer/client, tenant, and required scopes.
- An ID-token request denied and a wrong-tenant request denied, using a runtime
  credential handler that never prints bearer values or login credentials.

Do not log authorization headers, raw JWTs, refresh tokens, authorization codes,
passwords, or token-endpoint response bodies.

An access-token-backed tool result proves that this Sage API path works. It does
not prove Emil's ID-token-only API works or that his interim proxy can be removed.

## Sources

- [Claude remote connector setup](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [Claude OAuth requirements and callback](https://claude.com/docs/connectors/building/authentication)
- [Cognito pre-token generation versions](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-token-generation.html)

Remote connectors originate from Anthropic's infrastructure, including when used
in Claude Desktop. A localhost URL alone is insufficient.

## MCP deployment and rollback

Tenant_A MCP DEFAULT serves version 2. Only the code artifact changed; existing
authorizer, network, role, environment and header configuration were preserved.
The archive reuses the original ARM64 Python 3.13 dependencies. The previous
runtime version 1 remains the rollback target for DEFAULT. The original S3
source object is absent, so rollback should point DEFAULT at version 1 rather
than try to fetch that missing archive.

Live scripted verification is recorded in `claude-mcp-correlation-after.json`.
That dated snapshot predates the user's successful native Claude retry. The
user subsequently reported clean AXA product and claim calls, including
AXA Drive Protect (AXA-MOT-001). This is functional success; complete audience
binding, separate downstream credentials and native OAuth metadata compliance
remain to be demonstrated. Current design findings and outstanding tests are
recorded in [Emil authentication options](emil-authentication-options.md).
