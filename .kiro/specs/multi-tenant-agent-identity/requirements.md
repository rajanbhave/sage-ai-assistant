# Requirements Document

## Introduction

The Multi-Tenant Agent Identity feature defines Route C JWT passthrough for a proof of concept with exactly two demo tenants. Each demo tenant has an existing tenant-specific Amazon Cognito user pool and an independent Route C lane. A user authenticates with the Cognito user pool assigned to the selected lane, and the same original Cognito user access JWT remains the sole bearer credential through that lane's tenant-specific Agent Runtime endpoint and configuration, AgentCore Gateway, Sage MCP Runtime authorization chain, and the shared Sage API.

The two lanes may run the same Agent Application and Sage MCP codebase, but identity configuration and managed authorization remain lane-specific. Every AgentCore managed authorizer has exactly one OIDC discovery URL, and that URL belongs to the Cognito user pool assigned to the same lane. A token issued for one lane must fail at every managed door in the other lane before protected behavior. Exact bearer preservation is enforced at code-owned forwarding boundaries; managed services are verified through authorizer and target configuration plus behavioral authorization tests rather than adjacent managed ingress-and-egress byte comparisons.

The shared Sage API allowlists exactly the two demo tenant issuers. The Sage API may read an unverified issuer candidate only to choose a validation configuration after an exact match against the server-controlled issuer allowlist; the Sage API then independently verifies the token before using any claim as identity authority. The selected lane, verified issuer, and signed tenant claim must agree. Caller-controlled tenant values, prompts, and model output cannot select a lane, issuer, validation configuration, user, or tenant authority.

Route C does not introduce token exchange, downstream machine credentials, an on-behalf-of flow, a context-token broker, a second signed context token, or workload-token use. The language model does not receive authentication artifacts, and no component logs token values. Sage MCP and Sage API remain responsible for application tenant and permission checks, and Sage API remains the data-access and row-level-security boundary.

The proof of concept admits only an AgentCore Gateway HTTP passthrough target configured with `protocolType: MCP` and `JWT_PASSTHROUGH`. The target endpoint is the MCP_Runtime_Base_URL of the separately hosted Sage MCP Runtime, with the deployed qualifier supplied as a static query parameter; the Gateway appends the `invocations` path segment from the Gateway_Target_Invocation_URL. Each Runtime or Gateway custom JWT authorizer has one OIDC discovery URL.

### Task 14 simplification amendment

The requirements define observable security behavior and deployment gates, not a required class, callback, serializer, repository, state-machine, HTTP-framework, or test-fixture shape. Implementations may use direct functions, standard-library HTTP interfaces, immutable records, or deployment-owned JSON state when they preserve the acceptance criteria. The following are explicitly non-contractual implementation details: topology transition objects, in-memory configuration stores, protocol-proof value objects, callback-based authorization pipelines, generic repository/write extension points, recursive result projectors, private SDK subclasses, per-event binding copies, and credential-provenance variants that have no production caller. Tasks 13.3–13.5 must be rerun after this amendment because local manifest, dry-run, or preflight digests may change; no cloud mutation is authorized by this amendment.

## Architecture Route Taxonomy and Selection

- **Route A — OBO**: Uses an RFC 8693-capable authorization server to exchange identity at each downstream boundary and issue audience-specific user tokens. Route A requires a new authorization server because Amazon Cognito does not provide the required token-exchange capability.
- **Route B — M2M plus signed context**: Uses downstream Amazon Cognito M2M tokens together with a separately signed user-and-tenant context token. Route B requires custom broker, signing-key management, replay-protection, and M2M-to-context binding infrastructure.
- **Route C — JWT passthrough**: Uses the original tenant Cognito user access token as the sole bearer credential through every Route C Door, preserves the exact bearer at code-owned forwarding boundaries, configures Gateway with `JWT_PASSTHROUGH`, independently validates the JWT at authorization boundaries, and creates no replacement credential.

The Sage proof of concept selects Route C because it matches the existing same-JWT trust model and avoids Route A's new authorization server and Route B's custom token infrastructure. Route A and Route B are comparison alternatives rejected for this proof of concept, not implemented modes.

## Scope Boundary

### In Scope

- Exactly two fixed demo tenants, two tenant-specific Cognito user pools, and two parallel Route C lanes.
- Tenant-specific Frontend lane endpoints selected only from trusted deployment configuration.
- Cognito user access-token issuance with one signed canonical tenant claim and least-privilege API scopes.
- Exact bearer-token preservation at the Frontend, Agent Application, and Sage MCP code-owned forwarding boundaries.
- Independent JWT validation at every trust boundary against the issuer assigned to the selected lane.
- Cross-lane rejection of a token from either tenant at every managed door assigned to the other tenant.
- Shared Sage API validation against exactly two server-allowlisted tenant issuers with safe issuer-based configuration selection.
- Gateway target authorization with `JWT_PASSTHROUGH` on an AgentCore Gateway HTTP passthrough target configured with `protocolType: MCP` in each lane.
- Pre-activation proof of each lane's exact target endpoint, protocol, credential-provider, Cognito feature-plan, and PreTokenGeneration configuration.
- Conditional same-lane Gateway source restriction for Sage MCP Runtime only when AgentCore exposes a verifiable source signal for the exact Route C topology.
- Trusted user and tenant extraction from verified signed access-token claims.
- Sage MCP and Sage API tenant and permission checks.
- Sage API enforcement of data access and row-level security.
- Browser-owned access-token renewal and safe handling of token expiry during agent operations.
- Conversation clearing and late-result rejection after lane, tenant, subject, or session changes.
- Authentication-artifact exclusion from model context, logs, errors, Conversation content, and model-generated tool arguments.
- Route C compensating controls for shared-token blast radius, lack of per-hop audience separation, conditional same-lane Gateway source restriction, unconditional Sage API source restriction, and correlated operational audit.
- A proof gate and rollback topology for each lane.

### Out of Scope

- Production-scale dynamic tenancy, a third tenant, tenant self-service onboarding, and runtime creation of additional lanes.
- A single agent-facing Cognito pool, Cognito federation between demo tenants, or consolidation of tenant identity sources.
- Route C-M2M and other headless or public MCP client flows; these belong to `public-mcp-access`.
- MCP authorization policy and policy enforcement; these belong to `tenant-authorized-mcp-platform`.
- Detailed audit storage, retention, query, alerting, and dashboards; these belong to `agent-audit-observability`.
- On-behalf-of token exchange, per-hop audience tokens, cryptographic actor chains, and AgentCore Identity token-exchange APIs.
- OAuth credential providers and token-vault use for this interactive Route C path.
- Downstream M2M credentials, an M2M pool, static M2M Frontend fallback, and Phase 1 compatibility mode.
- A signed context token, Context Token Broker, replay store, or custom security-token service.
- Caller-provided tenant-header propagation or agent-constructed tenant-header authority.
- Public MCP onboarding, dynamic client registration, or tenant-agent account linking.
- Strands Skills, memory, product-core generation, write approval workflows, cost governance, and analytics.
- Direct database, S3, Athena, or other data-store credentials in the Agent Application or Sage MCP.

## Glossary

- **Multi_Tenant_Agent_Identity_System**: The complete two-lane Route C proof of concept spanning tenant-specific Cognito authentication, use of the original user access token as the sole bearer credential, exact preservation at code-owned forwarding boundaries, independent validation, identity extraction, browser session handling, and application authorization boundaries.
- **Demo_Tenant**: One of exactly two server-configured tenants in the proof of concept.
- **Tenant_A**: The first Demo Tenant and the owner of Tenant A Cognito Pool and Tenant A Route C Lane.
- **Tenant_B**: The second Demo Tenant and the owner of Tenant B Cognito Pool and Tenant B Route C Lane.
- **Route_A_OBO**: The rejected comparison route that requires an RFC 8693-capable authorization server and issues downstream audience-specific user tokens through on-behalf-of token exchange; Route A is not an implemented mode in the Sage proof of concept.
- **Route_B_M2M_Signed_Context**: The rejected comparison route that uses downstream Amazon Cognito M2M tokens plus a separately signed user-and-tenant context token and requires custom broker, signing-key management, replay-protection, and M2M-to-context binding infrastructure; Route B is not an implemented mode in the Sage proof of concept.
- **Route_C_JWT_Passthrough**: The selected proof-of-concept route in which one original tenant-specific Cognito user access JWT remains the sole bearer credential across the Selected Lane, code-owned forwarding boundaries preserve the exact received bearer without decoding, re-encoding, or substitution, Gateway uses `JWT_PASSTHROUGH`, and authorization boundaries independently validate the JWT.
- **Route_C_Interactive_User_Mode**: The requirements term for the implemented interactive-user mode of Route_C_JWT_Passthrough; existing acceptance-criteria references to Route_C_Interactive_User_Mode refer exclusively to Route_C_JWT_Passthrough.
- **Tenant_Cognito_Pool**: One tenant-specific Amazon Cognito user pool; the proof of concept has exactly two Tenant Cognito Pools and no federating agent-facing pool.
- **Tenant_Issuer**: The issuer identifier of one Tenant Cognito Pool.
- **Tenant_Discovery_URL**: The one OIDC discovery URL associated with one Tenant Issuer.
- **Tenant_Route_C_Lane**: One fixed chain containing a Demo Tenant, Tenant Cognito Pool, Tenant Issuer, Tenant Discovery URL, Frontend Lane Configuration, tenant-specific Agent Runtime endpoint and authorizer configuration, AgentCore Gateway and authorizer configuration, Sage MCP Runtime and authorizer configuration, Compatible Passthrough Target, and expected signed tenant value.
- **Tenant_A_Route_C_Lane**: The Tenant Route C Lane assigned to Tenant A.
- **Tenant_B_Route_C_Lane**: The Tenant Route C Lane assigned to Tenant B.
- **Selected_Lane**: The Tenant Route C Lane chosen by the Frontend from Trusted Lane Configuration for the current Authentication Session.
- **Trusted_Lane_Configuration**: The server-controlled deployment configuration containing exactly the Tenant A and Tenant B lane records and no caller-defined lane records.
- **Lane_Endpoint**: The tenant-specific Agent Runtime invocation endpoint stored in Trusted Lane Configuration.
- **Lane_Binding**: The required agreement among Selected Lane, Tenant Issuer, managed-authorizer Tenant Discovery URL, trusted client, and signed Canonical Tenant Claim.
- **Shared_Codebase**: Agent Application or Sage MCP source code that may be deployed in both lanes without sharing lane-specific identity configuration.
- **Frontend_App_Client**: A public Cognito app client assigned to one Tenant Cognito Pool and one Tenant Route C Lane; the app client has no client secret.
- **Trusted_Tenant_Assignment**: The exactly one server-controlled tenant identifier associated with an authenticated subject in the subject's Tenant Cognito Pool.
- **Trusted_Tenant_Assignment_Source**: The server-controlled Cognito administrative attribute source in one Tenant Cognito Pool used to resolve a Trusted Tenant Assignment.
- **Canonical_Tenant_Claim_Name**: The deployment-configured access-token claim name that carries the Trusted Tenant Assignment in both lanes.
- **Canonical_Tenant_Claim**: The exactly one non-empty string claim at the Canonical Tenant Claim Name in a User Access Token.
- **Expected_Lane_Tenant_Value**: The server-configured Canonical Tenant Claim value assigned to one Tenant Route C Lane.
- **Access_Token_Customizer**: The Cognito pre-token-generation trigger configured with event version `V2_0` in each Tenant Cognito Pool; the trigger adds the Canonical Tenant Claim and uses both `scopesToAdd` and `scopesToSuppress` to produce the Authorized Route C Scope Set.
- **Cognito_Feature_Plan**: The active feature plan of one Tenant Cognito Pool that must support `V2_0` PreTokenGeneration access-token customization before Route C activation.
- **PreTokenGeneration_Configuration**: The active trigger configuration of one Tenant Cognito Pool, including event version `V2_0`, used for access-token claim and scope customization.
- **User_Access_Token**: A Cognito-signed JWT issued by the Selected Lane's Tenant Cognito Pool; Cognito supplies `iss`, `exp`, `client_id`, `token_use=access`, `scope`, and `sub`, and the Access Token Customizer supplies exactly one Canonical Tenant Claim and the authorized Route C scope set.
- **Authentication_Session**: Browser state for one Selected Lane, authenticated subject, and tenant, including the current User Access Token and browser-controlled renewal material.
- **Valid_Authentication_Session**: An Authentication Session whose current User Access Token is unexpired, satisfies the Frontend's structural claim checks, and agrees with the Selected Lane.
- **Browser_Renewal_Material**: Authentication material retained and used only by the browser Authentication Session to renew or reacquire a User Access Token from the Selected Lane's Tenant Cognito Pool.
- **Route_C_Scope_Profile**: The configured least-privilege scope contract consisting of `sage-agent/invoke`, `sage-gateway/invoke`, `sage-mcp/invoke`, and `sage-api/read` for the currently deployed read-only Sage API.
- **Authorized_Route_C_Scope_Set**: The subset of Route C Scope Profile entries authorized for one authenticated subject and Frontend App Client; the final access-token scope set contains only these entries.
- **Non_Route_C_Cognito_Scope**: A default, hosted-UI, Cognito, OpenID Connect, or other scope not present in the Authorized Route C Scope Set for the token issuance event.
- **Required_Door_Scope**: The one scope from the Route C Scope Profile required by a specific Route C Door for the requested operation.
- **Lane_Trusted_Client_Set**: The server-controlled set of Frontend app-client identifiers permitted in one Tenant Route C Lane.
- **Accepted_Tenant_ID_Set**: The server-controlled set containing exactly Tenant A and Tenant B identifiers, recognized independently by Sage MCP and Sage API.
- **Allowed_Tenant_Issuer_Map**: The Sage API server-controlled map containing exactly the Tenant A and Tenant B issuer identifiers and their validation configurations.
- **Unverified_Issuer_Candidate**: The `iss` value read from a JWT before cryptographic verification solely to select a candidate Sage API validation configuration.
- **Presented_Tenant_Value**: A tenant value supplied in a prompt, payload field, query parameter, caller-controlled header, model output, model-generated tool argument, or other caller-controlled location.
- **Agent_Invocation**: One authenticated Frontend request to the Selected Lane's Agent Runtime.
- **Agent_Runtime**: The Amazon Bedrock AgentCore Runtime endpoint and managed authorizer configuration assigned to one Tenant Route C Lane and hosting the Agent Application.
- **Agent_Application**: The Sage orchestration code hosted by an Agent Runtime.
- **AgentCore_Gateway**: The tenant-lane Gateway and managed authorizer configuration through which the Agent Application invokes the lane's Sage MCP Runtime.
- **Sage_MCP_Runtime**: The tenant-lane AgentCore Runtime and managed authorizer configuration hosting Sage MCP.
- **Sage_MCP**: The application code hosted by Sage MCP Runtime.
- **Sage_API**: The shared customer API and SDK boundary that allowlists both Tenant Issuers, independently authorizes business operations, and enforces tenant data isolation and row-level security.
- **Managed_Route_C_Door**: One tenant-lane managed authorization boundary: Agent Runtime, AgentCore Gateway, or Sage MCP Runtime.
- **Route_C_Door**: One independently validating boundary: a Managed Route C Door or Sage API.
- **Runtime_JWT_Authorizer**: An AgentCore Runtime custom JWT authorizer configured with exactly one Tenant Discovery URL from the same Tenant Route C Lane, the Lane Trusted Client Set, the Runtime Required Door Scope, and fixed `customClaims` requiring `token_use EQUALS access` and `custom:tenant_id EQUALS Expected_Lane_Tenant_Value`.
- **Gateway_JWT_Authorizer**: An AgentCore Gateway custom JWT authorizer configured with exactly one Tenant Discovery URL from the same Tenant Route C Lane, the Lane Trusted Client Set, the Gateway Required Door Scope, and fixed `customClaims` requiring `token_use EQUALS access` and `custom:tenant_id EQUALS Expected_Lane_Tenant_Value`.
- **Proposed_Route_C_Configuration**: A candidate two-lane Route C issuer, lane, authorizer, scope, token-lifetime, target, API issuer-map, or routing configuration that is inactive until every applicable validation succeeds.
- **Last_Valid_Route_C_Configuration**: The most recently accepted two-lane Route C configuration; no such configuration exists before the first proposal is accepted.
- **Compatible_Passthrough_Target**: For this specification, an AgentCore Gateway HTTP passthrough target whose `targetConfiguration.http.passthrough.protocolType` equals `MCP`, whose credential-provider entry has `credentialProviderType` equal to `JWT_PASSTHROUGH`, and whose endpoint equals the MCP_Runtime_Base_URL of the separately hosted Sage MCP Runtime with the deployed qualifier supplied as a static query parameter.
- **Semantic_MCP_Target**: An AgentCore Gateway semantic MCP target; this target type is excluded from Route C because this specification requires the HTTP passthrough target form.
- **Route_C_Compatible_Topology**: A tenant-lane Gateway-to-Sage-MCP topology using a Compatible Passthrough Target whose HTTP endpoint invokes the separately hosted Sage MCP Runtime.
- **MCP_Runtime_Base_URL**: The Sage MCP Runtime base URL composed from the deployed AWS Region and URL-encoded Sage MCP Runtime ARN, carrying neither the `invocations` path segment nor a query string. This is the value configured as the passthrough target endpoint.
- **MCP_Runtime_Invocation_URL**: The documented Sage MCP Runtime invocation URL that the Gateway produces downstream, composed from the MCP_Runtime_Base_URL, the appended `invocations` path segment, and the deployed qualifier supplied as a static query parameter.
- **Gateway_Target_Invocation_URL**: The Gateway-side URL the Agent Application calls, composed from the lane Gateway URL, the target name, and the `invocations` path segment. A passthrough target forwards `/{targetName}/{path}` to `{endpoint}/{path}`, so the endpoint MUST NOT carry a query string; a query string on the endpoint would be split by the appended path.
- **Rollback_Route_C_Topology**: The last verified target and Gateway routing configuration preserved separately for one Tenant Route C Lane while a candidate topology is evaluated or activated.
- **JWT_PASSTHROUGH**: The Gateway target authorization mode that forwards the inbound bearer JWT to the downstream target without changing the token.
- **Authorization_Header**: The single HTTP `Authorization: Bearer <User_Access_Token>` header used between Route C Doors.
- **Bearer_Token_Bytes**: The byte sequence after the `Bearer ` scheme in an Authorization Header.
- **Code_Owned_Forwarding_Boundary**: A forwarding boundary implemented by the Frontend, Agent Application, or Sage MCP where the implementation controls extraction and forwarding of the Authorization Header and can verify exact bearer preservation without relying on managed-service ingress or egress byte visibility.
- **Credential_Bearing_Field**: A designated field that holds an Authorization Header, User Access Token, Browser Renewal Material, refresh token, or Auto Injected Workload Token.
- **Raw_Authentication_Artifact**: A value read from a Credential Bearing Field or a copy or transformation whose data provenance originates from a Credential Bearing Field.
- **Authentication_Artifact_Provenance**: The classification retained when a Raw Authentication Artifact is copied, transformed, nested, or propagated; classification depends on source field and data flow rather than field-name matching, value-substring matching, or JWT-format recognition.
- **Sink_Sanitization**: Provenance-based omission or complete-value redaction applied before content is written to model input, model output, model-generated tool arguments, tool results, UI content, logs, traces, exceptions, or errors.
- **Auto_Injected_Workload_Token**: A workload token that AgentCore Runtime may inject into runtime context; Route C does not consume the token.
- **Conversation**: Frontend-held messages, tool activity, streaming state, and other chat state associated with one Authentication Session.
- **Authenticated_Identity_Change**: A transition to a different Selected Lane, authenticated subject, or Canonical Tenant Claim.
- **Late_Result**: A response, stream event, tool event, error, or completion bound to an Authentication Session that has been replaced or terminated.
- **Sign_Out**: The user action or session outcome that terminates the current Authentication Session.
- **Configured_Access_Token_Lifetime**: The access-token lifetime configured for one Tenant Cognito Pool, approved by documented customer security policy, and recorded identically in that lane's security documentation.
- **Source_Signal_Proof_Gate**: The pre-activation determination of whether AgentCore exposes a verifiable request identity-chain or source signal for the exact Gateway HTTP passthrough with `protocolType: MCP` and `JWT_PASSTHROUGH` topology.
- **Verifiable_Gateway_Source_Signal**: An AgentCore-provided request identity-chain or source signal that can be configured and tested to distinguish the same lane's AgentCore Gateway as the Sage MCP Runtime caller; `allowedWorkloadConfiguration` is the candidate mechanism evaluated by the Source Signal Proof Gate.
- **Approved_Source_Path**: A customer-security-approved immediate upstream identity established by private ingress and injected into Sage API through trusted server context; caller headers and source IP addresses are never source authority.
- **Correlation_ID**: A non-secret identifier established once per Agent Invocation and propagated unchanged across Route C Doors for consumption by `agent-audit-observability`.
- **Identity_Error**: A stable non-secret response indicating failed authentication, lane binding, claim validation, tenant validation, scope validation, permission validation, source-path validation, or Route C configuration validation.
- **Protected_Behavior**: Model invocation, tool execution, downstream request, authorization decision, or tenant-data access or change.
- **Test_Suite**: The automated unit, property-based, component, configuration, and integration tests for this feature.

## Requirements

### Requirement 1: Exactly Two Tenant-Specific Route C Lanes

**User Story:** As a platform operator, I want two fixed tenant-specific Route C lanes, so that the proof of concept imitates the customer's existing tenant Cognito pools without a federating pool.

#### Acceptance Criteria

1. THE Multi_Tenant_Agent_Identity_System SHALL configure exactly two Demo_Tenants named Tenant_A and Tenant_B.
2. THE Multi_Tenant_Agent_Identity_System SHALL configure exactly two Tenant_Cognito_Pools with one pool assigned to Tenant_A and one pool assigned to Tenant_B.
3. THE Multi_Tenant_Agent_Identity_System SHALL configure exactly two Tenant_Route_C_Lanes with one lane assigned to Tenant_A and one lane assigned to Tenant_B.
4. THE Multi_Tenant_Agent_Identity_System SHALL exclude a shared agent-facing Cognito pool from Route_C_Interactive_User_Mode.
5. THE Multi_Tenant_Agent_Identity_System SHALL exclude federation between Tenant_A and Tenant_B identity sources from Route_C_Interactive_User_Mode.
6. THE Trusted_Lane_Configuration SHALL contain exactly one Tenant_Issuer and one Tenant_Discovery_URL for each Tenant_Route_C_Lane.
7. THE Trusted_Lane_Configuration SHALL bind each Tenant_Route_C_Lane to exactly one Lane_Endpoint, AgentCore_Gateway, Sage_MCP_Runtime, Expected_Lane_Tenant_Value, and Lane_Trusted_Client_Set.
8. THE Trusted_Lane_Configuration SHALL keep Tenant_A_Route_C_Lane values distinct from Tenant_B_Route_C_Lane values for tenant identifier, Tenant_Issuer, Tenant_Discovery_URL, and Lane_Endpoint.
9. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL set `iss` to the Tenant_Issuer assigned to the same Tenant_Route_C_Lane.
10. THE Multi_Tenant_Agent_Identity_System SHALL configure each Managed_Route_C_Door with exactly one Tenant_Discovery_URL belonging to the same Tenant_Route_C_Lane.
11. IF a Proposed_Route_C_Configuration contains fewer or more than two Demo_Tenants, Tenant_Cognito_Pools, or Tenant_Route_C_Lanes, THEN THE Multi_Tenant_Agent_Identity_System SHALL reject the proposal before activation.
12. IF a Proposed_Route_C_Configuration assigns more than one Tenant_Discovery_URL to a Managed_Route_C_Door, THEN THE Multi_Tenant_Agent_Identity_System SHALL reject the proposal before activation.
13. IF a Proposed_Route_C_Configuration assigns a Tenant_Issuer, Tenant_Discovery_URL, Lane_Endpoint, or Expected_Lane_Tenant_Value from one lane to a Managed_Route_C_Door in the other lane, THEN THE Multi_Tenant_Agent_Identity_System SHALL reject the proposal before activation.
14. IF the Multi_Tenant_Agent_Identity_System rejects a Proposed_Route_C_Configuration and a Last_Valid_Route_C_Configuration exists, THEN THE Multi_Tenant_Agent_Identity_System SHALL leave the Last_Valid_Route_C_Configuration unchanged and active.
15. IF the Multi_Tenant_Agent_Identity_System rejects a Proposed_Route_C_Configuration and no Last_Valid_Route_C_Configuration exists, THEN THE Multi_Tenant_Agent_Identity_System SHALL keep Route_C_Interactive_User_Mode disabled.
16. IF the Multi_Tenant_Agent_Identity_System rejects a Proposed_Route_C_Configuration, THEN THE Multi_Tenant_Agent_Identity_System SHALL return an Identity_Error identifying the violated two-lane constraint.

### Requirement 2: Tenant-Specific Cognito User Access-Token Issuance

**User Story:** As a tenant data owner, I want each tenant pool to issue a user access token with a signed lane-bound tenant claim, so that the selected lane carries the customer's existing identity context.

#### Acceptance Criteria

1. WHEN a Tenant_Cognito_Pool processes initial or renewed access-token generation for an authenticated interactive user, THE Tenant_Cognito_Pool SHALL invoke the Access_Token_Customizer with event version `V2_0` before token issuance.
2. WHEN the Access_Token_Customizer processes an access-token generation event, THE Access_Token_Customizer SHALL read the Trusted_Tenant_Assignment from the Trusted_Tenant_Assignment_Source assigned to the issuing Tenant_Cognito_Pool.
3. WHEN the Access_Token_Customizer resolves exactly one non-empty string Trusted_Tenant_Assignment equal to the issuing lane's Expected_Lane_Tenant_Value, THE Access_Token_Customizer SHALL set exactly one claim at the Canonical_Tenant_Claim_Name to that value.
4. THE Multi_Tenant_Agent_Identity_System SHALL configure exactly one Trusted_Tenant_Assignment_Source for each Tenant_Cognito_Pool.
5. THE Multi_Tenant_Agent_Identity_System SHALL configure one Canonical_Tenant_Claim_Name identically across both Tenant_Route_C_Lanes and Sage_API.
6. THE Multi_Tenant_Agent_Identity_System SHALL use User_Access_Tokens instead of Cognito ID tokens for Route C authorization.
7. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL supply exactly one `iss` claim equal to the lane's Tenant_Issuer.
8. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL supply exactly one `exp` claim from the lane's Configured_Access_Token_Lifetime.
9. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL supply exactly one non-empty string `sub` claim from the authenticated user record.
10. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL supply exactly one `client_id` claim belonging to the issuing lane's Lane_Trusted_Client_Set.
11. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL supply exactly one `token_use` claim with the value `access`.
12. WHEN the Access_Token_Customizer processes an access-token generation event, THE Access_Token_Customizer SHALL derive one Authorized_Route_C_Scope_Set containing only Route_C_Scope_Profile entries authorized for the authenticated subject and Frontend_App_Client.
13. WHEN the Access_Token_Customizer produces an access-token response, THE Access_Token_Customizer SHALL use `scopesToAdd` to add only Authorized_Route_C_Scope_Set entries absent from the incoming scope set.
14. WHEN the Access_Token_Customizer produces an access-token response, THE Access_Token_Customizer SHALL use `scopesToSuppress` to suppress every Non_Route_C_Cognito_Scope and every unauthorized Route_C_Scope_Profile entry present in the incoming scope set.
15. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL produce a final `scope` claim whose set of entries equals the Authorized_Route_C_Scope_Set.
16. WHEN the Access_Token_Customizer adds the Canonical_Tenant_Claim or customizes scopes, THE Access_Token_Customizer SHALL preserve Cognito-owned `iss`, `exp`, `sub`, `client_id`, and `token_use` claims unchanged and modify scope membership only through `scopesToAdd` and `scopesToSuppress`.
17. WHEN a Proposed_Route_C_Configuration is evaluated before activation, THE Multi_Tenant_Agent_Identity_System SHALL verify that the active Cognito_Feature_Plan of each of the two Tenant_Cognito_Pools supports `V2_0` access-token customization.
18. WHEN a Proposed_Route_C_Configuration is evaluated before activation, THE Multi_Tenant_Agent_Identity_System SHALL verify that each active PreTokenGeneration_Configuration uses event version `V2_0`, references a qualified Lambda alias or version, matches the approved handler and `CodeSha256`, and carries immutable lane configuration consistent with the pool, tenant, assignment source, client set, and grants.
19. IF either active Cognito_Feature_Plan or either active PreTokenGeneration_Configuration does not support the required `V2_0` access-token customization or cannot be verified, THEN THE Multi_Tenant_Agent_Identity_System SHALL reject the Proposed_Route_C_Configuration before activation.
20. IF the Access_Token_Customizer cannot resolve exactly one non-empty string Trusted_Tenant_Assignment equal to the issuing lane's Expected_Lane_Tenant_Value, THEN THE Tenant_Cognito_Pool SHALL reject Route C token issuance with an Identity_Error.
21. THE Access_Token_Customizer SHALL exclude Presented_Tenant_Values as sources or overrides of the Trusted_Tenant_Assignment.

### Requirement 3: Trusted Lane Selection and Browser Authentication Session

**User Story:** As a Sage user, I want the browser to select a configured tenant lane and manage my authentication session, so that untrusted content cannot choose an identity path and downstream components do not receive refresh credentials.

#### Acceptance Criteria

1. WHEN a user selects Tenant_A or Tenant_B through the Frontend, THE Frontend SHALL resolve exactly one Selected_Lane from the corresponding record in Trusted_Lane_Configuration.
2. IF a requested lane identifier does not exactly match Tenant_A or Tenant_B or does not resolve to exactly one Trusted_Lane_Configuration record, THEN THE Frontend SHALL reject the selection with an Identity_Error before authentication or a lane network request.
3. WHEN the Frontend initiates authentication, THE Frontend SHALL use only the Tenant_Cognito_Pool and Frontend_App_Client assigned to the Selected_Lane.
4. WHEN a user completes interactive authentication, THE Frontend SHALL establish a Valid_Authentication_Session only when the Tenant_Issuer, `client_id`, non-empty `sub`, and Canonical_Tenant_Claim agree with the Selected_Lane.
5. WHEN the Frontend sends an Agent_Invocation, THE Frontend SHALL send exactly one request to the Lane_Endpoint stored for the Authentication_Session's Selected_Lane in Trusted_Lane_Configuration.
6. WHEN the Frontend sends an Agent_Invocation, THE Frontend SHALL present the current User_Access_Token in the Authorization_Header.
7. IF a caller, prompt, payload, query parameter, caller-controlled header, model output, or model-generated tool argument supplies a tenant or lane value, THEN THE Frontend SHALL continue to select the Lane_Endpoint only from the current Authentication_Session and Trusted_Lane_Configuration.
8. IF the Frontend has no Valid_Authentication_Session, THEN THE Frontend SHALL reject the Agent_Invocation before sending a network request.
9. WHEN a User_Access_Token requires renewal or reacquisition, THE Frontend SHALL communicate only with the Tenant_Cognito_Pool assigned to the current Selected_Lane.
10. WHEN the Frontend renews or reacquires a User_Access_Token successfully, THE Frontend SHALL replace the expired or superseded User_Access_Token before the next Agent_Invocation.
11. WHEN the Frontend validates a renewed or reacquired User_Access_Token, THE Frontend SHALL require the Tenant_Issuer, `client_id`, `sub`, and Canonical_Tenant_Claim to equal the current Authentication_Session values and the Trusted_Lane_Configuration binding for the Selected_Lane.
12. IF a renewed or reacquired User_Access_Token fails the current issuer, client, subject, tenant, or Selected_Lane binding, THEN THE Frontend SHALL terminate the Authentication_Session.
13. IF browser renewal or reacquisition fails to produce a Valid_Authentication_Session, THEN THE Frontend SHALL terminate the Authentication_Session.
14. WHEN the Frontend terminates an Authentication_Session, THE Frontend SHALL remove the current User_Access_Token and Browser_Renewal_Material from active Frontend state.
15. WHEN the Frontend terminates an Authentication_Session, THE Frontend SHALL show the authentication form before accepting another Agent_Invocation.
16. THE Frontend SHALL confine Browser_Renewal_Material and refresh tokens to browser communication with the Selected_Lane's Tenant_Cognito_Pool.
17. THE Frontend SHALL exclude Browser_Renewal_Material and refresh tokens from every Agent_Invocation payload and header.
18. THE Agent_Application, Sage_MCP, and Sage_API SHALL exclude Browser_Renewal_Material and refresh tokens from acquisition, state, renewal, reacquisition, and downstream requests.
19. IF a Route_C_Door receives Browser_Renewal_Material or a refresh token, THEN THE receiving Route_C_Door SHALL reject the request before Protected_Behavior with an Identity_Error.

### Requirement 4: Unchanged JWT Propagation Within the Selected Lane

**User Story:** As a platform security owner, I want the same tenant Cognito access JWT propagated through the selected lane, so that each boundary authorizes the original user without custom token-minting infrastructure.

#### Acceptance Criteria

1. WHEN the Frontend sends an Agent_Invocation, THE Frontend SHALL send exactly one Authorization_Header whose Bearer_Token_Bytes equal the current User_Access_Token bytes.
2. THE Multi_Tenant_Agent_Identity_System SHALL use the original User_Access_Token sent by the Frontend as the sole bearer credential at every Route_C_Door and create zero replacement credentials for Route_C_Interactive_User_Mode.
3. WHEN the Agent_Application or Sage_MCP receives a Route C request from its hosting Runtime, THE receiving code-owned component SHALL accept exactly one Authorization_Header for forwarding.
4. WHEN the Agent_Application invokes the AgentCore_Gateway in the Selected_Lane, THE Agent_Application SHALL forward exactly the Bearer_Token_Bytes received from the Agent_Runtime without decoding, re-encoding, or substituting the bearer.
5. WHEN the AgentCore_Gateway invokes the Sage_MCP_Runtime in the Selected_Lane, THE AgentCore_Gateway SHALL use a target credential-provider entry whose `credentialProviderType` equals `JWT_PASSTHROUGH`.
6. WHEN the Sage_MCP invokes the Sage_API, THE Sage_MCP SHALL forward exactly the Bearer_Token_Bytes received from the Sage_MCP_Runtime without decoding, re-encoding, or substituting the bearer.
7. WHEN a code-owned component forwards a Route C request, THE code-owned component SHALL send exactly one Authorization_Header and zero additional credential-bearing headers or fields.
8. WHEN any component emits an application log, trace, exception, or error for Route_C_Interactive_User_Mode, THE Multi_Tenant_Agent_Identity_System SHALL include zero User_Access_Token values and zero Bearer_Token_Bytes.
9. THE Multi_Tenant_Agent_Identity_System SHALL initiate zero downstream M2M token-acquisition requests in Route_C_Interactive_User_Mode.
10. THE Multi_Tenant_Agent_Identity_System SHALL initiate zero AgentCore Identity token-exchange or on-behalf-of API calls in Route_C_Interactive_User_Mode.
11. THE AgentCore_Gateway SHALL configure zero OAuth credential providers for each Route C target.
12. THE Multi_Tenant_Agent_Identity_System SHALL create, accept, validate, forward, and use zero separate signed context tokens in Route_C_Interactive_User_Mode.
13. WHERE an Auto_Injected_Workload_Token is present, THE Agent_Application SHALL issue zero downstream requests containing or authenticated by the Auto_Injected_Workload_Token.
14. WHEN the Agent_Application or Sage_MCP forwards a Route C request, THE forwarding component SHALL send zero context-token fields, zero workload-token fields, and zero replacement-credential fields.
15. WHEN the Agent_Application or Sage_MCP forwards a Route C request, THE forwarding component SHALL forward zero tenant headers derived from a Presented_Tenant_Value.
16. IF the Agent_Application or Sage_MCP receives zero Authorization_Headers, more than one Authorization_Header, a scheme other than `Bearer`, an empty bearer, a syntactically invalid Authorization_Header, or a bearer that the component cannot forward exactly without decoding, re-encoding, or substitution, THEN THE receiving code-owned component SHALL reject the request before a downstream request with an Identity_Error.

### Requirement 5: Independent Lane-Specific Validation at Every Door

**User Story:** As a platform security owner, I want every Route C door to validate the bearer token against the selected lane, so that a token cannot cross from one tenant lane into the other.

#### Acceptance Criteria

1. WHEN a User_Access_Token reaches a Managed_Route_C_Door, THE corresponding managed JWT authorizer SHALL validate signature, issuer, and expiry against the one Tenant_Discovery_URL configured for that door's Tenant_Route_C_Lane.
2. WHEN a User_Access_Token reaches a Managed_Route_C_Door, THE corresponding managed JWT authorizer SHALL require `client_id` to match an entry in that lane's Lane_Trusted_Client_Set.
3. WHEN a User_Access_Token reaches a Managed_Route_C_Door, THE corresponding managed JWT authorizer SHALL require `token_use` to satisfy the fixed `customClaims` condition `EQUALS access`.
4. WHEN a User_Access_Token reaches a Managed_Route_C_Door, THE corresponding managed JWT authorizer SHALL require that door's Required_Door_Scope through configured `allowedScopes`.
5. WHEN a User_Access_Token reaches a Managed_Route_C_Door, THE corresponding managed JWT authorizer SHALL require `custom:tenant_id` to satisfy the fixed `customClaims` condition `EQUALS Expected_Lane_Tenant_Value` for that door's lane.
6. WHEN a Tenant_A token reaches a Tenant_B managed door, or a Tenant_B token reaches a Tenant_A managed door, THE corresponding managed JWT authorizer SHALL reject the request before Protected_Behavior.
7. WHEN a User_Access_Token reaches the Sage_API, THE Sage_API SHALL read only the Unverified_Issuer_Candidate before selecting a candidate validation configuration.
8. WHEN the Sage_API reads an Unverified_Issuer_Candidate, THE Sage_API SHALL require an exact match to one key in the Allowed_Tenant_Issuer_Map before selecting a validation configuration.
9. WHEN an Unverified_Issuer_Candidate matches one Allowed_Tenant_Issuer_Map key, THE Sage_API SHALL select only the validation configuration mapped to that exact key.
10. WHEN the Sage_API selects a candidate validation configuration, THE Sage_API SHALL independently validate signature, issuer, expiry, trusted client, `token_use=access`, and operation-specific Required_Door_Scope before using token claims as identity authority.
11. IF the Unverified_Issuer_Candidate is absent, non-string, empty, duplicated, or absent from the Allowed_Tenant_Issuer_Map, THEN THE Sage_API SHALL reject the request before Protected_Behavior with an Identity_Error.
12. IF cryptographic validation does not confirm the Tenant_Issuer used to select the Sage API validation configuration, THEN THE Sage_API SHALL reject the request before Protected_Behavior with an Identity_Error.
13. IF any Route_C_Door validation fails or cannot complete, THEN THE receiving Route_C_Door SHALL reject the request before Protected_Behavior with an Identity_Error.
14. THE Runtime_JWT_Authorizer and Gateway_JWT_Authorizer SHALL exclude Presented_Tenant_Value comparison, business-permission decisions, and actor-chain validation from managed-authorizer responsibility.
15. THE Agent_Application SHALL rely on the hosting Agent Runtime authorizer for signature, expiry, issuer, client, token type, managed scope, and managed tenant-claim validation; application code SHALL only preserve the original bearer and correlation ID for same-lane forwarding.
16. THE Sage_MCP SHALL rely on the hosting MCP Runtime authorizer for signature, expiry, issuer, client, token type, managed scope, and managed tenant-claim validation; application code SHALL only parse exactly one non-empty `sub` and Canonical_Tenant_Claim and require that tenant to equal the hosting lane before business processing.

### Requirement 6: Least-Privilege Scope Enforcement

**User Story:** As a customer security owner, I want each Route C door to enforce only the scopes required at that boundary, so that each unchanged tenant token has bounded authority.

#### Acceptance Criteria

1. THE Multi_Tenant_Agent_Identity_System SHALL define `sage-agent/invoke` as the Agent Runtime Required_Door_Scope in both Tenant_Route_C_Lanes.
2. THE Multi_Tenant_Agent_Identity_System SHALL define `sage-gateway/invoke` as the Gateway Required_Door_Scope in both Tenant_Route_C_Lanes.
3. THE Multi_Tenant_Agent_Identity_System SHALL define `sage-mcp/invoke` as the Sage MCP Runtime Required_Door_Scope in both Tenant_Route_C_Lanes.
4. THE Multi_Tenant_Agent_Identity_System SHALL define `sage-api/read` as the Sage API Required_Door_Scope for read operations.
5. IF a future Sage_API operation creates, updates, or deletes tenant data, THEN that endpoint SHALL define and enforce its own write authorization before implementation or deployment; the current deployable Sage_API exposes only product and claim reads.
6. WHEN a Managed_Route_C_Door receives a request, THE corresponding managed JWT authorizer SHALL enforce only that door's Required_Door_Scope through `allowedScopes`.
7. WHEN the Sage_API receives a request, THE Sage_API SHALL enforce the operation-specific Required_Door_Scope independently of upstream scope decisions.
8. IF a User_Access_Token lacks a Route_C_Door's Required_Door_Scope, THEN THE receiving Route_C_Door SHALL reject the request before Protected_Behavior with an Identity_Error.
9. WHEN a Tenant_Cognito_Pool issues a User_Access_Token, THE Tenant_Cognito_Pool SHALL include only Route_C_Scope_Profile entries authorized for the authenticated subject and lane Frontend_App_Client.
10. THE Multi_Tenant_Agent_Identity_System SHALL initiate zero replacement-bearer minting, exchange, or acquisition operations between Route_C_Doors.
11. THE Multi_Tenant_Agent_Identity_System SHALL validate the original User_Access_Token `client_id` against the selected lane's Lane_Trusted_Client_Set at every Route_C_Door.
12. THE Multi_Tenant_Agent_Identity_System SHALL document that Route_C_Interactive_User_Mode provides no hop-specific audience separation.

### Requirement 7: Cryptographic Lane, Tenant, and User Authority

**User Story:** As a tenant data owner, I want lane and tenant authority bound to verified token claims and trusted configuration, so that caller-controlled values cannot select another tenant or validation path.

#### Acceptance Criteria

1. WHEN the Sage_MCP receives a Runtime-validated User_Access_Token, THE Sage_MCP SHALL derive the authenticated user identifier from exactly one `sub` claim containing a non-empty string.
2. WHEN the Sage_MCP receives a Runtime-validated User_Access_Token, THE Sage_MCP SHALL derive the authenticated tenant identifier from exactly one Canonical_Tenant_Claim containing a non-empty string.
3. WHEN the Sage_MCP establishes application request identity after managed validation, THE Sage_MCP SHALL require the Canonical_Tenant_Claim to equal the hosting Tenant_Route_C_Lane's Expected_Lane_Tenant_Value.
4. WHEN the Sage_API validates a User_Access_Token, THE Sage_API SHALL derive the authenticated user identifier from exactly one verified `sub` claim containing a non-empty string.
5. WHEN the Sage_API validates a User_Access_Token, THE Sage_API SHALL derive the authenticated tenant identifier from exactly one verified Canonical_Tenant_Claim containing a non-empty string.
6. WHEN the Sage_API establishes request identity, THE Sage_API SHALL require the verified Tenant_Issuer and Canonical_Tenant_Claim to match the same entry in the server-controlled Allowed_Tenant_Issuer_Map.
7. IF the `sub` claim or Canonical_Tenant_Claim is absent, duplicated, non-string, empty, or whitespace-only, THEN THE Sage_MCP SHALL reject the request before invoking a Sage_API operation with an Identity_Error.
8. IF the verified `sub` claim or Canonical_Tenant_Claim is absent, duplicated, non-string, empty, or whitespace-only, THEN THE Sage_API SHALL reject the request before authorization or tenant-data access with an Identity_Error.
9. IF the Canonical_Tenant_Claim disagrees with the hosting Tenant_Route_C_Lane binding in Trusted_Lane_Configuration, THEN THE Sage_MCP SHALL reject the request before invoking a Sage_API operation with an Identity_Error.
10. IF the verified Tenant_Issuer and Canonical_Tenant_Claim do not map to the same Allowed_Tenant_Issuer_Map entry, THEN THE Sage_API SHALL reject the request before authorization or tenant-data access with an Identity_Error.
11. IF the Sage_MCP hosting lane is not exactly Tenant_A or Tenant_B, THEN THE Sage_MCP SHALL reject its deployment configuration before processing requests.
12. IF the Sage_API cannot independently confirm Canonical_Tenant_Claim membership in the Accepted_Tenant_ID_Set, THEN THE Sage_API SHALL reject the request before authorization or tenant-data access with an Identity_Error.
13. THE Sage_MCP SHALL exclude Presented_Tenant_Values from request-identity extraction and downstream tenant authority.
14. IF any Presented_Tenant_Value differs from the Canonical_Tenant_Claim as a case-sensitive string, THEN THE Sage_API SHALL reject the request before authorization or tenant-data access with an Identity_Error.
15. WHEN Sage_MCP application identity is established, THE Sage_MCP SHALL use only the managed-validated `sub`, Canonical_Tenant_Claim, and hosting Tenant_Route_C_Lane configuration as application identity authority.
16. WHEN every Presented_Tenant_Value equals the Canonical_Tenant_Claim, THE Sage_API SHALL continue to use only the verified Tenant_Issuer and Canonical_Tenant_Claim as identity authority.
17. THE Multi_Tenant_Agent_Identity_System SHALL exclude prompts, payload fields, query parameters, caller-controlled headers, model output, and model-generated tool arguments as lane, issuer, validation-configuration, user, or tenant authorities.
18. WHILE the Sage_MCP processes a request, THE Sage_MCP SHALL preserve the `sub` and Canonical_Tenant_Claim values established at request acceptance and the original bearer for exact forwarding.
19. WHILE the Sage_API processes a request, THE Sage_API SHALL preserve the verified Tenant_Issuer, `sub`, and Canonical_Tenant_Claim values established at request acceptance.

### Requirement 8: Shared Sage API Data and Permission Boundary

**User Story:** As a customer platform owner, I want the shared Sage API to remain the final authorization and data-isolation boundary for both lanes, so that the agent path preserves existing application controls.

#### Acceptance Criteria

1. THE Allowed_Tenant_Issuer_Map SHALL contain exactly two entries keyed by the Tenant_A and Tenant_B issuer identifiers and no other keys.
2. THE Allowed_Tenant_Issuer_Map SHALL bind each Tenant_Issuer to exactly one Expected_Lane_Tenant_Value and Lane_Trusted_Client_Set.
3. WHEN the Sage_MCP requires customer business data, THE Sage_MCP SHALL invoke the Sage_API instead of accessing the underlying data store directly.
4. WHEN the Sage_MCP requests a Sage_API operation, THE Sage_MCP SHALL preserve the validated User_Access_Token as the Sage_API bearer credential.
5. WHEN the Sage_API receives a request, THE Sage_API SHALL independently validate the User_Access_Token before subject authorization, tenant authorization, tenant-isolation establishment, or tenant-data access or change.
6. WHEN the Sage_API independently validates a User_Access_Token, THE Sage_API SHALL independently authorize the authenticated subject for the requested operation before tenant authorization, tenant-isolation establishment, or tenant-data access or change.
7. WHEN the Sage_API independently authorizes the authenticated subject, THE Sage_API SHALL independently authorize the Canonical_Tenant_Claim for the requested tenant resource before tenant-isolation establishment or tenant-data access or change.
8. WHEN token validation, subject authorization, and tenant authorization succeed for pooled relational data, THE Sage_API SHALL establish and verify row-level-security context derived from the Canonical_Tenant_Claim before executing a read or change.
9. WHEN token validation, subject authorization, and tenant authorization succeed for tenant-scoped non-relational data, THE Sage_API SHALL establish and verify the existing tenant-isolation control derived from the Canonical_Tenant_Claim before executing a read or change.
10. IF User_Access_Token validation fails or cannot complete, THEN THE Sage_API SHALL reject the operation before tenant-data access or change with an Identity_Error.
11. IF subject authorization, tenant authorization, or tenant-isolation verification fails or cannot complete, THEN THE Sage_API SHALL reject the operation before tenant-data access or change with an Identity_Error.
12. THE Agent_Application SHALL exclude direct customer data-store credentials from Route_C_Interactive_User_Mode.
13. THE Sage_MCP SHALL exclude direct customer data-store credentials from Route_C_Interactive_User_Mode.
14. IF the Sage_API is unavailable or a Sage_API request fails or cannot complete, THEN THE Sage_MCP SHALL return a non-secret operation failure and perform zero direct customer data-store access for the affected operation.

### Requirement 9: Compatible Gateway Target Topology Per Lane

**User Story:** As a platform operator, I want each Route C lane deployed only on a passthrough-compatible target topology, so that neither lane relies on unsupported semantic MCP target behavior.

#### Acceptance Criteria

1. WHEN a candidate target is evaluated for a Tenant_Route_C_Lane, THE Multi_Tenant_Agent_Identity_System SHALL classify the target as a Compatible_Passthrough_Target only when the target uses `targetConfiguration.http.passthrough.protocolType` equal to `MCP`.
2. WHEN a candidate target is evaluated for a Tenant_Route_C_Lane, THE Multi_Tenant_Agent_Identity_System SHALL record the current official AWS documentation reference and retrieval date supporting Gateway HTTP passthrough with `protocolType: MCP` and `JWT_PASSTHROUGH`.
3. WHEN a candidate Compatible_Passthrough_Target is evaluated before activation, THE Multi_Tenant_Agent_Identity_System SHALL verify that the deployed target type is Gateway HTTP passthrough and that `targetConfiguration.http.passthrough.protocolType` equals `MCP` in the deployed target configuration.
4. WHEN a candidate Compatible_Passthrough_Target is evaluated before activation, THE Multi_Tenant_Agent_Identity_System SHALL verify that the target credential-provider entry has `credentialProviderType` equal to `JWT_PASSTHROUGH` in the deployed target configuration.
5. WHEN a candidate Compatible_Passthrough_Target is evaluated before activation, THE Multi_Tenant_Agent_Identity_System SHALL verify that the configured endpoint equals the MCP_Runtime_Base_URL composed from the deployed AWS Region and URL-encoded Sage_MCP_Runtime ARN for the same Tenant_Route_C_Lane, that the endpoint carries no query string, and that the deployed qualifier is supplied as a static query parameter.
6. IF a candidate target uses an AgentCore Runtime target type, Semantic_MCP_Target type, or any target type other than Gateway HTTP passthrough with `protocolType: MCP`, THEN THE Multi_Tenant_Agent_Identity_System SHALL reject the Proposed_Route_C_Configuration before activation.
7. THE Multi_Tenant_Agent_Identity_System SHALL exclude an AgentCore Runtime target type as an alternative Compatible_Passthrough_Target for this specification.
8. THE Multi_Tenant_Agent_Identity_System SHALL exclude an in-place `JWT_PASSTHROUGH` assumption or configuration change for a Semantic_MCP_Target.
9. WHEN migration from a Semantic_MCP_Target begins in a Tenant_Route_C_Lane, THE Multi_Tenant_Agent_Identity_System SHALL preserve that lane's existing verified target and Gateway routing configuration as the Rollback_Route_C_Topology.
10. WHEN a candidate Compatible_Passthrough_Target is selected, THE Multi_Tenant_Agent_Identity_System SHALL verify MCP initialization through that lane's AgentCore_Gateway before activation.
11. WHEN a candidate Compatible_Passthrough_Target is selected, THE Multi_Tenant_Agent_Identity_System SHALL verify tool listing through that lane's AgentCore_Gateway before activation.
12. WHEN a candidate Compatible_Passthrough_Target is selected, THE Multi_Tenant_Agent_Identity_System SHALL verify a predefined non-mutating tool invocation through that lane's AgentCore_Gateway before activation.
13. WHEN a candidate Compatible_Passthrough_Target is selected, THE Multi_Tenant_Agent_Identity_System SHALL verify complete ordered streamed-result delivery through that lane's AgentCore_Gateway before activation.
14. WHEN a candidate Compatible_Passthrough_Target is selected, THE Multi_Tenant_Agent_Identity_System SHALL verify rejection of the other lane's User_Access_Token before activation.
15. IF a candidate target-configuration, documentation, protocol, or cross-lane verification fails or cannot complete, THEN THE Multi_Tenant_Agent_Identity_System SHALL keep Route_C_Interactive_User_Mode disabled on the candidate topology.
16. IF a candidate target-configuration, documentation, protocol, or cross-lane verification fails or cannot complete, THEN THE Multi_Tenant_Agent_Identity_System SHALL leave that lane's Rollback_Route_C_Topology unchanged and active.
17. WHEN a candidate passes every target-configuration, documentation, protocol, and cross-lane verification, THE Multi_Tenant_Agent_Identity_System SHALL preserve that lane's Rollback_Route_C_Topology while activating the candidate topology.
18. IF a Route C acceptance check fails after candidate activation, THEN THE Multi_Tenant_Agent_Identity_System SHALL restore and verify the affected lane's Rollback_Route_C_Topology.
19. IF a Route C acceptance check fails after candidate activation in one Tenant_Route_C_Lane, THEN THE Multi_Tenant_Agent_Identity_System SHALL leave the other Tenant_Route_C_Lane's active and rollback topologies unchanged.

### Requirement 10: Token Expiry and Long-Running Operations

**User Story:** As a Sage user, I want expired credentials to fail safely, so that downstream components do not refresh or reuse an invalid user token.

#### Acceptance Criteria

1. IF the current time is at or after the `exp` value when a User_Access_Token reaches a Route_C_Door, THEN THE receiving Route_C_Door SHALL reject the request before any requested operation, including a data-changing operation.
2. IF a downstream Route_C_Door returns an authentication failure caused by User_Access_Token expiry, THEN THE Agent_Application SHALL terminate the affected Agent_Invocation.
3. IF a downstream Route_C_Door returns an authentication failure caused by User_Access_Token expiry, THEN THE Agent_Application SHALL issue zero additional downstream operations for the affected Agent_Invocation.
4. IF User_Access_Token expiry interrupts an Agent_Invocation, THEN THE Agent_Application SHALL return a non-secret session-expired result as the final result of that Agent_Invocation.
5. WHEN the Frontend receives a session-expired result, THE Frontend SHALL renew or reacquire the User_Access_Token from the current Selected_Lane's Tenant_Cognito_Pool before permitting another attempt.
6. WHEN the Frontend retries an operation interrupted by expiry, THE Frontend SHALL submit the retry as a new Agent_Invocation to the same Selected_Lane carrying the renewed or reacquired User_Access_Token.
7. IF an expiry-interrupted operation creates, updates, or deletes data, THEN THE Frontend SHALL require explicit user action before submitting a new Agent_Invocation.
8. IF an expiry-interrupted operation creates, updates, or deletes data, THEN THE Frontend SHALL exclude automatic replay of that operation.
9. THE Agent_Application SHALL exclude User_Access_Token renewal, reacquisition, and refresh-token use from operation and retry handling.
10. THE Sage_MCP SHALL exclude User_Access_Token renewal, reacquisition, and refresh-token use from operation and retry handling.
11. THE Sage_API SHALL exclude User_Access_Token renewal, reacquisition, and refresh-token use from request handling.
12. WHILE Route_C_Interactive_User_Mode is active, THE Multi_Tenant_Agent_Identity_System SHALL confine User_Access_Token renewal and reacquisition to the Frontend browser Authentication_Session.

### Requirement 11: Conversation and Lane Isolation

**User Story:** As a Sage user, I want chat state isolated by authenticated lane and identity, so that content from another tenant, lane, or user cannot remain active after a transition.

#### Acceptance Criteria

1. WHEN the Frontend accepts an Agent_Invocation, THE Frontend SHALL bind the Agent_Invocation and every streamed response, tool, error, completion, and cancellation event to the Authentication_Session, Selected_Lane, `sub`, and Canonical_Tenant_Claim captured at acceptance.
2. WHEN an Authenticated_Identity_Change occurs, THE Frontend SHALL clear the Conversation before accepting a message or response event under the new Authentication_Session.
3. WHEN an Authenticated_Identity_Change occurs, THE Frontend SHALL discard every Late_Result bound to the prior Authentication_Session without modifying the Conversation.
4. WHERE active Agent_Invocation cancellation is supported, WHEN an Authenticated_Identity_Change occurs, THE Frontend SHALL request cancellation of each active Agent_Invocation bound to the prior Authentication_Session.
5. WHEN Sign_Out occurs, THE Frontend SHALL clear the Conversation before Sign_Out completes.
6. WHEN Sign_Out occurs, THE Frontend SHALL remove the current Authentication_Session from active Frontend state before Sign_Out completes.
7. WHEN Sign_Out occurs, THE Frontend SHALL discard every Late_Result bound to the terminated Authentication_Session without modifying the Conversation.
8. WHERE active Agent_Invocation cancellation is supported, WHEN Sign_Out occurs, THE Frontend SHALL request cancellation of each active Agent_Invocation bound to the terminated Authentication_Session.
9. WHILE an Authenticated_Identity_Change is in progress and the new Authentication_Session is not valid, THE Frontend SHALL reject new Agent_Invocations without modifying the Conversation.
10. WHEN a User_Access_Token is renewed and the renewed token's Tenant_Issuer, `client_id`, `sub`, and Canonical_Tenant_Claim equal the current Authentication_Session values and Selected_Lane binding, THE Frontend SHALL preserve the Conversation.
11. WHILE the Frontend has no Valid_Authentication_Session, THE Frontend SHALL keep the Conversation empty.
12. WHILE the Frontend has no Valid_Authentication_Session, THE Frontend SHALL reject new Agent_Invocations without modifying the Conversation.
13. IF a streamed response, tool, error, completion, or cancellation event is not bound to the current Valid_Authentication_Session, Selected_Lane, `sub`, and Canonical_Tenant_Claim, THEN THE Frontend SHALL discard the event without modifying the Conversation.

### Requirement 12: Authentication-Artifact Non-Observability

**User Story:** As a customer security owner, I want raw authentication artifacts outside model-controlled and observable content, so that the language model and routine telemetry cannot disclose reusable credentials.

#### Acceptance Criteria

1. THE Multi_Tenant_Agent_Identity_System SHALL designate Authorization Header fields, User Access Token fields, Browser Renewal Material fields, refresh-token fields, and Auto Injected Workload Token fields as Credential_Bearing_Fields.
2. WHEN a value from a Credential_Bearing_Field is copied, transformed, nested, or propagated, THE Multi_Tenant_Agent_Identity_System SHALL preserve Authentication_Artifact_Provenance for the resulting value.
3. THE Multi_Tenant_Agent_Identity_System SHALL exclude field-name substring matching, value-substring matching, and JWT-format recognition as Authentication_Artifact_Provenance classification mechanisms.
4. WHEN the Agent_Application constructs model input, THE Agent_Application SHALL omit every Credential_Bearing_Field and every value carrying Authentication_Artifact_Provenance, including every Raw_Authentication_Artifact, at every nesting level.
5. WHEN the Agent_Application processes model output, THE Agent_Application SHALL omit every Credential_Bearing_Field and every value carrying Authentication_Artifact_Provenance, including every Raw_Authentication_Artifact, before returning, retaining, or forwarding the output.
6. WHEN the Agent_Application constructs model-generated tool arguments, THE Agent_Application SHALL omit every Credential_Bearing_Field and every value carrying Authentication_Artifact_Provenance, including every Raw_Authentication_Artifact, at every nesting level.
7. WHEN the Sage_MCP returns a tool result or tool error to the language model, THE Sage_MCP SHALL omit every Credential_Bearing_Field and every value carrying Authentication_Artifact_Provenance, including every Raw_Authentication_Artifact, at every nesting level.
8. WHEN the Frontend renders or retains Conversation, tool-activity, request-activity, or error content, THE Frontend SHALL omit every Credential_Bearing_Field and every value carrying Authentication_Artifact_Provenance, including every Raw_Authentication_Artifact.
9. WHEN any component emits an application log or trace, THE Multi_Tenant_Agent_Identity_System SHALL omit each value carrying Authentication_Artifact_Provenance, including each Raw_Authentication_Artifact, or replace the complete value with a constant non-secret redaction indicator.
10. WHEN any component creates or propagates an exception, THE Multi_Tenant_Agent_Identity_System SHALL omit each value carrying Authentication_Artifact_Provenance, including each Raw_Authentication_Artifact, from exception messages, structured exception fields, nested causes, and rendered stack traces.
11. IF authentication, lane binding, tenant, scope, permission, tool, or downstream processing fails, THEN THE Multi_Tenant_Agent_Identity_System SHALL return a non-secret error containing zero Credential_Bearing_Fields and zero values carrying Authentication_Artifact_Provenance, including zero Raw_Authentication_Artifacts.
12. WHEN a Route C request crosses a Route_C_Door, THE Multi_Tenant_Agent_Identity_System SHALL preserve the User_Access_Token in the trusted Authorization_Header transport field.
13. WHEN a value carrying Authentication_Artifact_Provenance, including a Raw_Authentication_Artifact, leaves trusted Route C transport handling, THE Multi_Tenant_Agent_Identity_System SHALL apply Sink_Sanitization before the value is written to model input, model output, model-generated tool arguments, tool results, UI content, logs, traces, exceptions, or errors.
14. WHERE an Auto_Injected_Workload_Token is present, THE Agent_Application SHALL exclude the token and every value carrying Authentication_Artifact_Provenance derived from the token from model input, model output, tool arguments, tool results, downstream requests, UI content, logs, traces, exceptions, and errors.

### Requirement 13: Route C Compensating Controls and Audit Boundary

**User Story:** As a regulated customer security owner, I want the two-lane Route C trade-offs bounded by explicit controls, so that the shared-token architecture has a reviewable security posture.

#### Acceptance Criteria

1. THE Multi_Tenant_Agent_Identity_System SHALL document that compromise of a User_Access_Token can affect every Route_C_Door in the issuing token's Tenant_Route_C_Lane that accepts the shared token during the token lifetime.
2. THE Multi_Tenant_Agent_Identity_System SHALL configure one Configured_Access_Token_Lifetime for each Tenant_Cognito_Pool approved by documented customer security policy.
3. THE Multi_Tenant_Agent_Identity_System SHALL document the approved Configured_Access_Token_Lifetime for each Tenant_Route_C_Lane.
4. THE Multi_Tenant_Agent_Identity_System SHALL keep each documented access-token lifetime exactly equal to the corresponding active Tenant_Cognito_Pool value.
5. IF the current time reaches the `exp` value in a User_Access_Token, THEN THE receiving Route_C_Door SHALL reject further use of the User_Access_Token before Protected_Behavior.
6. WHEN an expired User_Access_Token requires another attempt, THE Frontend SHALL require browser reacquisition or renewal from the current Selected_Lane before a new Agent_Invocation.
7. THE Multi_Tenant_Agent_Identity_System SHALL use Required_Door_Scopes to bound the shared-token blast radius in each lane.
8. WHEN a Proposed_Route_C_Configuration is evaluated before activation, THE Source_Signal_Proof_Gate SHALL determine whether AgentCore exposes a Verifiable_Gateway_Source_Signal for the exact Gateway HTTP passthrough with `protocolType: MCP` and `JWT_PASSTHROUGH` topology, including evaluation of `allowedWorkloadConfiguration` as the candidate mechanism.
9. WHEN the Source_Signal_Proof_Gate completes, THE Multi_Tenant_Agent_Identity_System SHALL record the documentation evidence, deployed configuration evidence, and verification result used to classify the Verifiable_Gateway_Source_Signal as available or unavailable.
10. WHERE the Source_Signal_Proof_Gate confirms a Verifiable_Gateway_Source_Signal, THE Multi_Tenant_Agent_Identity_System SHALL configure and verify the documented AgentCore mechanism to restrict each Sage_MCP_Runtime to the AgentCore_Gateway assigned to the same Tenant_Route_C_Lane.
11. WHERE the Source_Signal_Proof_Gate confirms a Verifiable_Gateway_Source_Signal, IF a request reaches Sage_MCP_Runtime without the verified same-lane AgentCore_Gateway identity or source signal, THEN THE Sage_MCP_Runtime SHALL reject the request before Protected_Behavior with an Identity_Error.
12. WHERE the Source_Signal_Proof_Gate determines that no Verifiable_Gateway_Source_Signal is available, THE Multi_Tenant_Agent_Identity_System SHALL record the Sage_MCP_Runtime same-lane Gateway source control as unavailable for the proof of concept.
13. WHERE the Source_Signal_Proof_Gate determines that no Verifiable_Gateway_Source_Signal is available, THE Multi_Tenant_Agent_Identity_System SHALL make no claim that Sage_MCP_Runtime enforces a same-lane Gateway source restriction.
14. THE Sage_MCP_Runtime SHALL enforce lane-specific JWT issuer, trusted client, `token_use=access`, Required_Door_Scope, and cross-lane rejection controls independently of the Source_Signal_Proof_Gate result.
15. THE Multi_Tenant_Agent_Identity_System SHALL restrict Sage_API access to customer-approved source identities injected by private ingress as trusted server context; caller headers and source IP addresses SHALL NOT confer source authority.
16. IF a request reaches Sage_API from a source outside the documented Approved_Source_Paths, THEN THE Sage_API SHALL reject the request before Protected_Behavior with an Identity_Error.
17. WHEN an Agent_Invocation begins, THE Frontend or Agent_Application SHALL establish exactly one Correlation_ID containing no Raw_Authentication_Artifact.
18. WHEN a Route C request crosses a Route_C_Door, THE Multi_Tenant_Agent_Identity_System SHALL preserve the Correlation_ID unchanged.
19. WHEN a Route_C_Door accepts a request or rejects a request after establishing authenticated identity, THE receiving Route_C_Door SHALL make the Correlation_ID, Route_C_Door identity, Tenant_Route_C_Lane identity, authenticated subject, Canonical_Tenant_Claim, and authorization outcome available to `agent-audit-observability` without Raw_Authentication_Artifacts.
20. THE Multi_Tenant_Agent_Identity_System SHALL classify Route C actor evidence as correlated operational audit rather than a cryptographic on-behalf-of actor chain.
21. THE Multi_Tenant_Agent_Identity_System SHALL exclude cryptographic actor-chain claims from Route_C_Interactive_User_Mode.
22. THE Multi_Tenant_Agent_Identity_System SHALL leave audit persistence, retention, search, alerting, and reporting to `agent-audit-observability`.

### Requirement 14: Two-Lane Route C Identity Verification

**User Story:** As an engineer, I want automated verification of both Route C lanes and the shared API boundary, so that configuration or code changes cannot silently restore an untrusted tenant or token path.

#### Acceptance Criteria

1. WHEN lane-configuration tests run, THE Test_Suite SHALL verify exactly two Demo_Tenants, two Tenant_Cognito_Pools, and two Tenant_Route_C_Lanes.
2. WHEN lane-configuration tests run, THE Test_Suite SHALL verify one tenant-specific issuer, discovery URL, Frontend app client, Lane Endpoint, Agent Runtime configuration, Gateway configuration, Sage MCP Runtime configuration, and Expected Lane Tenant Value per lane.
3. WHEN lane-configuration tests run, THE Test_Suite SHALL verify that each Managed_Route_C_Door has exactly one Tenant_Discovery_URL belonging to the same Tenant_Route_C_Lane.
4. WHEN lane-configuration tests run, THE Test_Suite SHALL verify absence of an agent-facing Cognito pool, cross-tenant federation, a third tenant, and dynamic lane onboarding.
5. WHEN rejected-configuration tests run, THE Test_Suite SHALL verify rejection before activation and unchanged preservation of the Last_Valid_Route_C_Configuration.
6. WHEN rejected-configuration tests run without a Last_Valid_Route_C_Configuration, THE Test_Suite SHALL verify that Route_C_Interactive_User_Mode remains disabled.
7. WHEN access-token tests run, THE Test_Suite SHALL verify the source, exact cardinality, type, and required value of `iss`, `exp`, `client_id`, `token_use`, `scope`, `sub`, and the Canonical_Tenant_Claim in each lane, including exact equality between the final scope set and the Authorized_Route_C_Scope_Set.
8. WHEN access-token tests run, THE Test_Suite SHALL verify rejection of Cognito ID tokens in both Tenant_Route_C_Lanes.
9. WHEN access-token-customization tests run, THE Test_Suite SHALL verify that both active Cognito_Feature_Plans support `V2_0`, both active PreTokenGeneration_Configurations use `V2_0`, the Access_Token_Customizer reads the lane Trusted_Tenant_Assignment_Source, `scopesToAdd` adds only authorized Route C scopes, `scopesToSuppress` removes every Non_Route_C_Cognito_Scope and unauthorized Route C scope, the final scope set equals the Authorized_Route_C_Scope_Set, Cognito-owned non-scope claims remain unchanged, one Canonical_Tenant_Claim equals Expected_Lane_Tenant_Value, and Presented_Tenant_Values are excluded.
10. WHEN Frontend lane-selection tests generate supported, unknown, malformed, and caller-controlled lane or tenant values, THE Test_Suite SHALL verify exact resolution of one trusted lane record, exact selection of that record's Lane_Endpoint, and rejection before authentication or network access when exact resolution fails.
11. WHEN browser-session tests run, THE Test_Suite SHALL verify lane-specific renewal or reacquisition, current-token replacement, preservation of issuer, client, subject, tenant, and Selected_Lane binding, fail-closed renewal failure, and zero Browser_Renewal_Material outside browser communication with the Selected_Lane's Tenant_Cognito_Pool.
12. WHEN passthrough tests run, THE Test_Suite SHALL compare exact Bearer_Token_Bytes only at controlled Code_Owned_Forwarding_Boundaries by verifying exactly one Authorization_Header per forwarding request, the Frontend sends the current User_Access_Token, the Agent_Application forwards the bearer received from Agent_Runtime without decoding, re-encoding, or substitution, and Sage_MCP forwards the bearer received from Sage_MCP_Runtime without decoding, re-encoding, or substitution.
13. WHEN managed-authorizer configuration tests run, THE Test_Suite SHALL inspect deployed configuration to verify the lane Tenant_Discovery_URL, Lane_Trusted_Client_Set, local Required_Door_Scope, and fixed `token_use EQUALS access` rule at every Managed_Route_C_Door.
14. WHEN cross-lane rejection tests run, THE Test_Suite SHALL verify that a Tenant_A token fails at Tenant_B Agent_Runtime, AgentCore_Gateway, and Sage_MCP_Runtime before Protected_Behavior.
15. WHEN cross-lane rejection tests run, THE Test_Suite SHALL verify that a Tenant_B token fails at Tenant_A Agent_Runtime, AgentCore_Gateway, and Sage_MCP_Runtime before Protected_Behavior.
16. WHEN managed-authorizer boundary tests run, THE Test_Suite SHALL verify that managed authorizers perform zero dynamic tenant-membership, Presented_Tenant_Value, permission, or actor-chain decisions.
17. WHEN Sage API issuer-selection tests generate issuer candidates, THE Test_Suite SHALL verify exact allowlist matching before validation-configuration selection and rejection of absent, duplicate, non-string, empty, unknown, or nonmatching issuers.
18. WHEN Sage API independent-validation tests run, THE Test_Suite SHALL verify cryptographic confirmation of the selected issuer configuration before any verified claim becomes identity authority.
19. WHEN least-privilege-scope tests run, THE Test_Suite SHALL verify `sage-agent/invoke`, `sage-gateway/invoke`, `sage-mcp/invoke`, and `sage-api/read` at the defined boundaries in both lanes. IF a future mutating Sage_API endpoint is added, its own write authorization and focused tests SHALL be added with that endpoint.
20. WHEN lane-authority property tests generate Selected_Lanes, verified issuers, signed tenant claims, trusted clients, subjects, and Presented_Tenant_Values, THE Test_Suite SHALL verify that identity is established only when the Selected_Lane, verified Tenant_Issuer, trusted `client_id`, current `sub`, and signed Canonical_Tenant_Claim agree with the same Trusted_Lane_Configuration record.
21. WHEN caller-authority property tests generate Presented_Tenant_Values, THE Test_Suite SHALL verify that prompts, payloads, query parameters, caller-controlled headers, model output, and tool arguments cannot change lane, issuer configuration, subject, or tenant authority.
22. WHEN Sage API boundary tests run, THE Test_Suite SHALL verify exactly two allowlisted issuers and independent token, operation, subject, tenant, row-level-security, and non-relational tenant-isolation checks before tenant-data access or change.
23. WHEN Sage API boundary and unavailability tests run, THE Test_Suite SHALL verify Sage_MCP data access only through Sage_API, zero direct customer data-store credentials in Agent_Application and Sage_MCP, and zero direct customer data-store access after Sage_API unavailability or request failure.
24. WHEN target-capability and target-configuration tests run, THE Test_Suite SHALL inspect each deployed target and verify that the deployed target type is Gateway HTTP passthrough, the official-documentation evidence identifies support for Gateway HTTP passthrough with `protocolType: MCP` and `JWT_PASSTHROUGH` and records the evidence retrieval date, `targetConfiguration.http.passthrough.protocolType` equals `MCP`, a credential-provider entry has `credentialProviderType` equal to `JWT_PASSTHROUGH`, and the endpoint equals the MCP_Runtime_Base_URL for the deployed Region and URL-encoded Sage_MCP_Runtime ARN with the qualifier supplied as a static query parameter and no query string on the endpoint.
25. WHEN target-protocol tests run, THE Test_Suite SHALL verify MCP initialization, tool listing, non-mutating tool invocation, complete ordered streamed results, and other-lane token rejection through the Gateway HTTP passthrough target before candidate activation.
26. WHEN target-migration tests run, THE Test_Suite SHALL verify separate unchanged preservation and successful restoration of each lane's Rollback_Route_C_Topology after capability, protocol, cross-lane, or post-activation failure and unchanged active and rollback topologies in the unaffected lane.
27. WHEN forbidden-path and forwarding-boundary tests run, THE Test_Suite SHALL verify exactly one Authorization_Header per Route C request, fail-closed rejection of missing, duplicate, malformed, or non-preservable bearer input at each Code_Owned_Forwarding_Boundary, zero replacement credentials, zero downstream M2M token requests, zero token-exchange or on-behalf-of calls, zero OAuth credential-provider uses, zero signed-context-token paths, zero Auto_Injected_Workload_Token uses, zero downstream renewal paths, and zero caller-provided tenant-header propagation.
28. WHEN token-expiry tests run, THE Test_Suite SHALL verify operation termination, zero additional downstream operations, browser-only lane-specific renewal or reacquisition, retry as a new Agent_Invocation, and zero automatic replay of an operation that can change data.
29. WHEN Conversation-isolation tests run, THE Test_Suite SHALL verify Authentication_Session, Selected_Lane, subject, and tenant binding for streamed response, tool, error, completion, and cancellation events; Conversation clearing; cancellation requests where supported; same-identity renewal preservation; and Late_Result rejection without Conversation modification.
30. WHEN authentication-artifact classification tests run, THE Test_Suite SHALL verify Credential_Bearing_Field and Authentication_Artifact_Provenance classification without field-name substring matching, value-substring matching, or JWT-format recognition.
31. WHEN authentication-artifact sink tests run, THE Test_Suite SHALL verify provenance-based Sink_Sanitization before model input, model output, model-generated tool arguments, tool results, UI content, logs, traces, exceptions, and Identity_Error responses; zero User_Access_Token values and zero Bearer_Token_Bytes in logs, traces, exceptions, and errors; and unchanged trusted Authorization_Header transport at Code_Owned_Forwarding_Boundaries.
32. WHEN token-lifetime configuration tests run, THE Test_Suite SHALL verify customer-security-policy approval and exact agreement between documented and active Configured_Access_Token_Lifetime values for both Tenant_Cognito_Pools without imposing an unapproved numeric bound.
33. WHEN Sage MCP Runtime source-control tests run, THE Test_Suite SHALL verify that the Source_Signal_Proof_Gate treats `allowedWorkloadConfiguration` and any documented equivalent only as candidate mechanisms and classifies a Verifiable_Gateway_Source_Signal as available only when documentation evidence, deployed configuration evidence, and behavioral verification prove applicability to the exact Gateway HTTP passthrough with `protocolType: MCP` and `JWT_PASSTHROUGH` topology.
34. WHERE the Source_Signal_Proof_Gate confirms a Verifiable_Gateway_Source_Signal, WHEN Sage MCP Runtime source-control tests run, THE Test_Suite SHALL verify deployed same-lane AgentCore Gateway source restriction and rejection of requests lacking the verified same-lane source signal before Protected_Behavior.
35. WHERE the Source_Signal_Proof_Gate determines that no Verifiable_Gateway_Source_Signal is available, WHEN Sage MCP Runtime source-control tests run, THE Test_Suite SHALL verify that the control is recorded as unavailable for the proof of concept and that no same-lane Gateway source-restriction claim is made.
36. WHEN source-control tests run, THE Test_Suite SHALL verify unconditional Sage MCP Runtime issuer, trusted-client, `token_use=access`, Required_Door_Scope, and cross-lane rejection controls and unconditional Sage_API Approved_Source_Path rejection before Protected_Behavior.
37. WHEN correlation tests run, THE Test_Suite SHALL verify exactly one non-secret Correlation_ID per Agent_Invocation, unchanged propagation across the Selected_Lane's Route_C_Doors, and availability of the same value and lane identity to `agent-audit-observability`.
38. WHEN Route C security-posture tests run, THE Test_Suite SHALL verify documentation of per-lane shared-token blast radius, absence of hop-specific audience separation, correlated operational actor evidence, absence of cryptographic actor-chain claims, and the audit responsibility boundary.


### Demonstration-build amendment to Requirement 3.5

Requirement 3.5 states that the Frontend sends exactly one request to the
Lane_Endpoint stored for the Authentication_Session's Selected_Lane. This
amendment scopes one exception for demonstration builds only.

1. WHERE a build sets `VITE_DEMO_STAGE` to `true`, THE Frontend MAY send exactly
   one deliberate Cross_Lane_Rejection_Probe to the Agent Runtime endpoint of the
   lane that is not the Selected_Lane, for the sole purpose of demonstrating that
   the managed authorizer of the other lane denies the current bearer.
2. THE Cross_Lane_Rejection_Probe SHALL read only the HTTP status of the response
   and SHALL NOT read, render, store, or log the response body, so an unexpected
   success cannot place another tenant's content in the user interface.
3. THE Cross_Lane_Rejection_Probe SHALL be refused at its call site when
   `VITE_DEMO_STAGE` is absent or not `true`, in addition to not being reachable
   from the user interface in that case.
4. THE Cross_Lane_Rejection_Probe SHALL send only the current access token and one
   correlation identifier, and SHALL NOT send Browser_Renewal_Material.
5. IF a build serves real users, THEN `VITE_DEMO_STAGE` SHALL be absent or `false`
   and THE Frontend SHALL satisfy Requirement 3.5 without exception.
6. THE Cross_Lane_Rejection_Probe SHALL NOT be treated as evidence of any control
   other than the other lane's managed inbound authorization decision.

Implementation: `frontend/src/lib/demo/cross-lane-probe.ts`, gated by
`frontend/src/lib/demo/config.ts` and by the demo-stage toggle in
`frontend/src/App.tsx`.
