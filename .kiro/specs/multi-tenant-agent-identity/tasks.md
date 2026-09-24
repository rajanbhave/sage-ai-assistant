# Implementation Plan: Multi-Tenant Agent Identity

## Overview

Incrementally migrate the current Sage AI Assistant from its shared-pool, ID-token, tenant-header, Agent-to-Gateway M2M path to the finalized two-lane Route C design. Reuse the existing Agent, FastMCP, React, deployment-script, pytest/Hypothesis, and Cognito client structure; add only the missing shared Sage API and Route C identity modules. Each step must preserve exactly two fixed tenant lanes, the original user access-token bearer, fail-closed validation, lane-local topology state, browser-only renewal, and provenance-safe sinks.

## Tasks

- [x] 1. Establish shared Route C contracts and validation foundations
  - [x] 1.1 Add the required automated-test entry points
    - Add non-watch backend and frontend test scripts using the existing pytest/Hypothesis stack and pinned Vitest/fast-check development dependencies.
    - Keep backend and frontend test configuration minimal and compatible with the existing `uv` and Vite projects.
    - _Requirements: 14.1–14.38_

  - [x] 1.2 Implement immutable two-lane configuration models and atomic validation
    - Add Python models for the two lane records, per-door authorizers, exact two-entry API issuer map, target evidence, lane topology state, approved token lifetime, source-proof record, and approved source paths.
    - Validate exactly Tenant A and Tenant B; distinct pools, issuers, discovery URLs, endpoints, and expected tenant values; one same-lane discovery URL per managed door; and one canonical tenant claim name.
    - Reject invalid proposals without mutating the last valid configuration, or leave Route C disabled before the first valid proposal.
    - _Requirements: 1.1–1.16, 8.1–8.2, 13.2–13.4_

  - [x] 1.3 Implement typed authentication transport, safe errors, and correlation primitives
    - Add immutable authentication-artifact provenance wrappers, strict single-Bearer-header parsing/building, stable non-secret identity errors, and one opaque correlation ID per invocation.
    - Permit unwrapping only into trusted Authorization transport; provide positive safe-field serializers for model, tool, UI, log, trace, exception, and error sinks.
    - Do not classify artifacts with field-name matching, value matching, or JWT-shape detection.
    - _Requirements: 4.3, 4.7–4.8, 4.16, 12.1–12.14, 13.17–13.19_

  - [x] 1.4 Write the property test for exact atomic two-lane configuration
    - **Property 1: Two-lane configuration acceptance is exact, atomic, and lane-consistent**
    - Generate lane cardinalities, cross-lane swaps, duplicate/missing bindings, managed-door discovery lists, and prior-configuration states.
    - **Validates: Requirements 1.1–1.3, 1.6–1.15, 14.1–14.6**

  - [x] 1.5 Add focused tests for transport parsing, safe errors, and provenance propagation
    - Cover missing, duplicate, malformed, wrong-scheme, empty, and non-preservable Authorization input; complete-value redaction; nested provenance; and credential-free correlation IDs.
    - _Requirements: 4.3, 4.7–4.8, 4.16, 12.1–12.3, 12.9–12.13, 13.17, 14.27, 14.30–14.31_

- [x] 2. Replace shared Cognito identity with two pool-specific access-token issuers
  - [x] 2.1 Implement the `V2_0` pre-token-generation access-token customizer
    - Resolve the trusted tenant only from the issuing pool's administrative assignment source and require exact agreement with that lane's expected tenant.
    - Emit exactly one canonical tenant claim; derive the authorized Route C scope set; use `scopesToAdd` only for missing authorized scopes and `scopesToSuppress` for every non-Route-C or unauthorized scope.
    - Preserve Cognito-owned `iss`, `exp`, `sub`, `client_id`, and `token_use`; reject caller-presented tenant overrides and invalid assignment cardinality.
    - _Requirements: 2.1–2.16, 2.20–2.21, 6.9_

  - [x] 2.2 Refactor `scripts/deploy_user_pool.py` for exactly two existing tenant pools
    - Remove the shared agent-facing pool and ID-token assumptions; configure one public client, trusted assignment source, Route C resource scopes, and `V2_0` customizer per tenant pool.
    - Before any mutation or activation, verify both active Cognito feature plans and both active PreTokenGeneration configurations support and invoke `V2_0` access-token customization.
    - Emit exactly two immutable trusted-lane records and machine-readable approved/active token-lifetime evidence without inventing a numeric limit.
    - _Requirements: 1.1–1.10, 2.4–2.6, 2.17–2.19, 3.3, 6.1–6.5, 13.2–13.4, 14.1–14.4, 14.32_

  - [x] 2.3 Write the property test for trusted token customization
    - **Property 2: Token customization derives one lane tenant claim and exact authorized scopes only from trusted pool state**
    - Generate initial/renewal events, assignment-source results, feature-plan and trigger states, incoming/authorized scope sets, caller values, and Cognito-owned claims.
    - **Validates: Requirements 2.1–2.5, 2.12–2.21, 14.7, 14.9**

  - [x] 2.4 Add focused Cognito configuration and issuance tests
    - Verify two distinct pools and issuers, access-token use, one claim of each required type, exact final scope equality, `scopesToAdd`/`scopesToSuppress`, protected-claim preservation, both-pool `V2_0` proof, and ID-token rejection.
    - _Requirements: 1.2, 1.9, 2.1–2.21, 6.9, 14.7–14.9, 14.32_

- [x] 3. Implement trusted frontend lane sessions and browser-only renewal
  - [x] 3.1 Refactor frontend authentication around a fixed two-record lane registry
    - Update `frontend/src/lib/auth/cognito.ts`, `LoginScreen.tsx`, and `App.tsx` to resolve only exact Tenant A or Tenant B records containing distinct pool, client, issuer, endpoint, and expected tenant values.
    - Use Cognito access tokens rather than ID tokens; establish a session only when issuer, client, non-empty subject, signed tenant, expiry, and selected lane agree.
    - Remove shared-pool, free-form tenant, static bearer, and Phase 1 fallback paths; sign-out must clear active credentials before returning to authentication.
    - _Requirements: 3.1–3.4, 3.8, 3.14–3.15, 4.2, 6.11, 11.5–11.6_

  - [x] 3.2 Refactor `frontend/src/lib/agentcore-client/client.ts` for lane-bound invocation
    - Accept an immutable invocation binding and send only to the current session's configured lane endpoint.
    - Emit exactly one Authorization header with bearer bytes equal to the current access token and one non-secret correlation header; send no tenant-authority header, refresh material, or fallback credential.
    - Accept an `AbortSignal`, surface stable expiry separately from other failures, and preserve ordered SSE delivery.
    - _Requirements: 3.5–3.8, 3.17, 4.1, 4.7, 4.15, 10.4, 11.1, 13.17–13.18_

  - [x] 3.3 Implement renewal, expiry retry, and conversation-binding state in `ChatInterface.tsx`
    - Renew or reacquire only through the selected lane's pool and require unchanged issuer, client, subject, tenant, and lane before preserving the session and Conversation.
    - Bind every stream/tool/error/completion/cancellation event to session, lane, subject, and tenant; clear on identity change or sign-out and discard late mismatched events.
    - Terminate expiry-interrupted invocations, permit only a new invocation after renewal, and require explicit user action for mutating retries with no automatic write replay.
    - _Requirements: 3.9–3.18, 10.2–10.12, 11.1–11.13_

  - [x] 3.4 Add frontend positive sink schemas and credential-safe rendering
    - Sanitize streamed tool arguments/results, errors, and retained Conversation content by provenance before UI state mutation or rendering.
    - Ensure access tokens and browser renewal material remain only in typed authentication state and selected-pool communication, never component props intended for display or serialized invocation payloads.
    - _Requirements: 3.16–3.19, 12.4–12.5, 12.8, 12.11, 12.13_

  - [x] 3.5 Write the property test for browser lane and session binding
    - **Property 3: Browser lane and session binding cannot be redirected by caller content**
    - Generate supported, unknown, malformed, and caller-supplied lane/tenant values plus authentication and renewal claim sets.
    - **Validates: Requirements 3.1–3.18, 14.10–14.11**

  - [x] 3.6 Write the property test for expiry and write replay
    - **Property 11: Expiry terminates one invocation and never automatically replays a write**
    - Generate expiry positions, downstream sequences, lane sessions, and read/write operation classes.
    - **Validates: Requirements 10.1–10.12, 14.28**

  - [x] 3.7 Write the property test for conversation isolation
    - **Property 12: Conversation accepts events only from the current lane-bound identity**
    - Generate renewals, identity changes, sign-outs, abort races, and every stream event type; mismatched events must leave state unchanged.
    - **Validates: Requirements 11.1–11.13, 14.29**

  - [x] 3.8 Add focused frontend component and transport tests
    - Verify invalid lane resolution performs no authentication/network call, access-token equality at Frontend emission, selected endpoint use, browser-only renewal, same-identity renewal preservation, identity-change clearing, cancellation, late-event rejection, and safe UI errors.
    - _Requirements: 3.1–3.19, 4.1, 10.5–10.8, 11.1–11.13, 12.8, 14.10–14.12, 14.28–14.31_

- [x] 4. Checkpoint — validate identity issuance and frontend session behavior
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Replace Agent-side credential acquisition with exact bearer forwarding
  - [x] 5.1 Refactor `agent/agent.py` to forward the original Route C bearer
    - Parse exactly one Runtime-forwarded Authorization header, retain the exact bearer bytes in the typed transport wrapper, and call only the lane-configured target-specific Gateway URL with that bearer and unchanged correlation ID.
    - Remove JWT-derived tenant-header authority, Phase 1 header fallback, M2M token acquisition/cache, OAuth client-secret environment variables, and every exchange/OBO/context/workload-token path.
    - Rely on the Agent Runtime managed authorizer for signature, expiry, issuer, client, token type, local scope, and expected tenant validation; do not decode claims or use AgentCore Identity replacement-token decorators.
    - _Requirements: 4.2–4.4, 4.7–4.16, 5.15, 6.1, 6.10, 7.17, 10.2–10.4, 10.9, 13.18_

  - [x] 5.2 Apply provenance-safe Agent model, tool, stream, log, and exception boundaries
    - Build model input from explicit safe fields only, omit transport artifacts from model output and generated tool arguments, and return stable non-secret expiry and request failures.
    - Stop an expiry-failed invocation immediately with zero additional downstream operations.
    - _Requirements: 4.8, 10.2–10.4, 12.4–12.6, 12.9–12.11, 12.13–12.14_

  - [x] 5.3 Add focused Agent transport and forbidden-path tests
    - Spy on downstream calls to prove exact incoming/outgoing bearer equality at the Agent code-owned boundary, one Authorization header, unchanged correlation, and zero M2M, exchange, OAuth, context, workload, refresh, or tenant-header calls.
    - Verify malformed bearer and expiry failures occur before model or Gateway activity and expose no artifact in logs/errors.
    - _Requirements: 4.3–4.4, 4.7–4.16, 10.2–10.4, 12.4–12.6, 12.9–12.14, 14.12, 14.27–14.31_

- [x] 6. Render and deploy six lane-specific managed authorizers
  - [x] 6.1 Implement a same-lane authorizer renderer
    - Render Agent Runtime, Gateway, and MCP Runtime authorizers separately for each lane with exactly one same-lane discovery URL, lane trusted clients, fixed `token_use EQUALS access`, fixed `custom:tenant_id EQUALS expected tenant`, and only the local required scope.
    - Exclude dynamic tenant membership, presented-tenant comparison, permission, and actor-chain decisions from managed authorizers.
    - _Requirements: 1.10, 5.1–5.4, 5.14, 6.1–6.3, 6.6, 14.3, 14.13, 14.16_

  - [x] 6.2 Refactor `deploy_agent.sh` and `deploy_mcp.sh` for two isolated lane deployments
    - Configure and launch the shared codebase twice with lane-specific Runtime names, discovery URLs, trusted clients, local scopes, endpoints, expected tenant values, and Authorization/correlation header allowlists.
    - Remove M2M pool/client fallbacks and tenant-header allowlists; make MCP Runtime issuer, client, access-token type, local scope, and cross-lane rejection unconditional.
    - Apply a same-lane Gateway source restriction only when a proven Source Signal Proof Record authorizes it; otherwise record the control unavailable and make no restriction claim.
    - _Requirements: 1.3, 1.7–1.10, 4.13–4.15, 5.1–5.6, 6.1–6.3, 13.10–13.14_

  - [x] 6.3 Write the property test for managed-door lane validation
    - **Property 5: Managed doors validate only their own lane and reject the other lane**
    - Generate both-lane authorizer records and token claim combinations, including cross-lane issuer/client/scope/type cases.
    - **Validates: Requirements 5.1–5.6, 5.13–5.16, 14.13–14.16**

  - [x] 6.4 Add focused authorizer configuration and cross-lane tests
    - Inspect all six rendered/deployed configurations for one same-lane discovery URL, client set, local scope, and token-use rule; verify both directions of rejection before application sentinels.
    - Verify no managed authorizer performs tenant-membership, presented-value, permission, or actor-chain decisions.
    - _Requirements: 5.1–5.6, 5.13–5.16, 6.6, 14.13–14.16, 14.36_

- [x] 7. Replace the semantic/OAuth Gateway path with lane-local HTTP MCP passthrough
  - [x] 7.1 Refactor `scripts/deploy_gateway.py` to create two compatible passthrough targets
    - Remove the M2M Cognito pool, client-credentials flow, OAuth credential provider, and semantic MCP target activation path.
    - For each separate Gateway, create only an HTTP passthrough target whose `targetConfiguration.http.passthrough.protocolType` is `MCP` and whose credential provider is exactly `JWT_PASSTHROUGH`.
    - Compose and verify the exact MCP Runtime invocation URL from deployed Region, URL-encoded lane Runtime ARN, and deployed qualifier; reject AgentCore Runtime targets, semantic targets, near-match endpoints, and missing qualifiers.
    - _Requirements: 4.5, 4.11, 9.1, 9.3–9.8, 14.24_

  - [x] 7.2 Implement lane-local candidate, active, and rollback topology transitions
    - Preserve each lane's previously verified target, route, and Agent Gateway URL before evaluating a candidate; activate or restore only the affected lane.
    - Keep the other lane's active, candidate, rollback, enabled, and routing state unchanged on every failure and post-activation rollback.
    - _Requirements: 9.9, 9.15–9.19, 14.26_

  - [x] 7.3 Implement target evidence, protocol proof, and conditional source-signal evaluation
    - Record current official HTTP-MCP/JWT-passthrough documentation URL and actual retrieval date, deployed target evidence, and endpoint equality before activation.
    - Add automated lane proof checks for MCP initialize, direct tool listing, predefined non-mutating invocation, complete ordered streaming, and other-lane token rejection.
    - Evaluate `allowedWorkloadConfiguration` and documented equivalents only as Source Signal Proof Gate candidates; classify a same-lane source signal available only from documentation, deployed configuration, and behavioral proof.
    - _Requirements: 9.2–9.5, 9.10–9.17, 13.8–13.14, 14.24–14.25, 14.33–14.35_

  - [x] 7.4 Write the property test for compatible target activation and rollback
    - **Property 10: Only Gateway HTTP MCP passthrough can activate, with lane-local rollback**
    - Generate target shapes, URL components, evidence, protocol outcomes, cross-lane outcomes, and independent lane topology transitions.
    - **Validates: Requirements 9.1–9.19, 14.24–14.26**

  - [x] 7.5 Add focused Gateway target and topology configuration tests
    - Assert exact target shape, `MCP`, `JWT_PASSTHROUGH`, zero OAuth providers, exact encoded Runtime URL, candidate-disabled failure behavior, rollback preservation, and unaffected-lane equality.
    - Do not compare bearer bytes across adjacent managed Gateway and MCP Runtime boundaries; inspect configuration and behavioral authorization instead.
    - _Requirements: 4.5, 4.11, 9.1–9.19, 14.24–14.27_

- [x] 8. Checkpoint — validate Agent, authorizer, and Gateway Route C configuration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Establish Sage MCP lane identity and same-bearer Sage API calls
  - [x] 9.1 Implement pair-preserving MCP request identity validation
    - Read injected HTTP headers through `headers: dict = CurrentHeaders()`, parse the Runtime-validated bearer without overwriting duplicate claims, and require exactly one non-empty subject and canonical tenant claim.
    - Rely on the MCP Runtime managed authorizer for signature, expiry, issuer, client, token type, local scope, and expected tenant validation; require only the extracted tenant and hosting lane to agree in application code.
    - Remove caller tenant-header authority from `mcp_server/tools/data_tools.py`.
    - _Requirements: 5.16, 7.1–7.3, 7.7, 7.9, 7.11, 7.13, 7.15, 7.17–7.18_

  - [x] 9.2 Replace direct mock-data access with a same-bearer Sage API client
    - Preserve existing tool registration and semantic descriptions, but route every business-data operation through the configured shared Sage API using the exact received bearer and correlation ID.
    - Send no derived tenant-authority, renewal, context, workload, or replacement-credential fields; retain no direct datastore credentials or fallback path.
    - _Requirements: 4.6–4.7, 4.14–4.15, 8.3–8.4, 8.12–8.14, 10.10, 13.18_

  - [x] 9.3 Apply provenance-safe MCP tool result, error, log, and exception schemas
    - Return only positive safe-field tool results and stable non-secret failures; sanitize nested artifacts before model-facing results, telemetry, or exceptions.
    - If Sage API is unavailable or fails, return a safe operation failure and perform zero direct data access.
    - _Requirements: 8.14, 12.7, 12.9–12.13_

  - [x] 9.4 Write the property test for managed validation and application identity binding
    - **Property 8: Managed validation plus subject, tenant, and hosting lane are the only identity authority**
    - Generate pair-preserving subject/tenant claim sets and hosting-lane records; established application identity must remain immutable without duplicating platform authentication.
    - **Validates: Requirements 7.1–7.19, 14.20–14.21**

  - [x] 9.5 Add focused MCP identity, forwarding, and API-failure tests
    - Cover duplicate/malformed subject and tenant claims, lane/tenant mismatch, exact code-owned bearer forwarding, safe tool output, and zero direct access after API failure.
    - _Requirements: 4.6–4.7, 7.1–7.3, 7.7, 7.9, 7.11, 7.13, 7.15, 7.17–7.18, 8.3–8.4, 8.12–8.14, 14.12, 14.20–14.23_

- [x] 10. Implement the shared Sage API authorization and isolation boundary
  - [x] 10.1 Implement exact issuer selection and independent JWT validation
    - Add a shared Sage API component with an immutable map containing exactly the two tenant issuers and no default/dynamic entry.
    - Parse only one non-empty unverified `iss` candidate for exact map lookup, then independently verify signature, the same issuer, expiry, trusted `client_id`, `token_use=access`, operation scope, one subject, and one signed tenant before creating identity.
    - Reject absent, duplicate, malformed, unknown, near-match, or cryptographically unconfirmed issuers before protected behavior.
    - _Requirements: 5.7–5.13, 7.4–7.6, 7.8, 7.10, 8.1–8.5_

  - [x] 10.2 Implement ordered API authorization and unconditional source controls
    - Enforce the operation-specific read/write scope, then subject permission, then tenant-resource authorization, then isolation setup; false or indeterminate results must execute zero data operations.
    - Unconditionally reject requests outside the two Sage MCP Approved Source Paths and approved customer-application paths, independent of the conditional MCP Runtime source-signal result.
    - Preserve identity and correlation throughout the request and emit only non-secret audit boundary fields.
    - _Requirements: 6.4–6.8, 7.19, 8.5–8.11, 13.15–13.21_

  - [x] 10.3 Move tenant data behind API-owned isolation enforcement
    - Relocate the current demo data access behind the Sage API boundary; establish and verify tenant-derived RLS context for relational operations and the existing tenant-isolation control for non-relational operations before every read/change.
    - Ensure Agent Application and Sage MCP contain no datastore credential or direct/fallback data path.
    - _Requirements: 8.3, 8.6–8.14, 14.22–14.23_

  - [x] 10.4 Write the property test for exact API issuer selection
    - **Property 6: Shared API issuer selection is exact and unverified claims never become authority**
    - Generate encoded payloads with duplicate/malformed issuer keys and fixed map entries; require complete verification before identity creation.
    - **Validates: Requirements 5.7–5.13, 14.17–14.18**

  - [x] 10.5 Write the property test for least-privilege scopes
    - **Property 7: Each door enforces exactly its required least-privilege scope**
    - Generate authorized/issued scope sets, door types, operations, clients, and tokens; missing local or operation scope must block protected behavior.
    - **Validates: Requirements 6.1–6.9, 6.11, 14.19**

  - [x] 10.6 Write the property test for the fail-closed Sage API boundary
    - **Property 9: Sage API is the fail-closed permission and tenant-data boundary**
    - Generate token, subject, tenant, operation, source, permission, API-availability, and isolation outcomes; any false/indeterminate result must produce zero direct or fallback data operations.
    - **Validates: Requirements 8.1–8.14, 14.22–14.23**

  - [x] 10.7 Add focused API issuer, ordering, scope, source, and isolation tests
    - Verify the exact two-key map, malicious issuer candidates, cryptographic confirmation, read/write scopes, validation→subject→tenant→isolation order, approved-source rejection, RLS/non-relational context, and safe failures.
    - _Requirements: 5.7–5.13, 6.4–6.8, 7.4–7.19, 8.1–8.14, 13.15–13.16, 14.17–14.23, 14.36_

- [x] 11. Wire Route C together and complete required verification
  - [x] 11.1 Write the property test for unchanged code-owned bearer forwarding
    - **Property 4: Code-owned forwarding preserves the original bearer and excludes replacement paths**
    - Compare complete bearer bytes only at Frontend emission, Agent forwarding, and Sage MCP forwarding; verify Gateway-to-MCP Runtime through `JWT_PASSTHROUGH` configuration and behavior only.
    - Generate malformed transport and forbidden credential-path cases and assert zero downstream operation on failure.
    - **Validates: Requirements 4.1–4.16, 6.10, 14.12, 14.27**

  - [x] 11.2 Write the property test for authentication-artifact provenance
    - **Property 13: Authentication-artifact provenance permits only trusted transport**
    - Generate arbitrary copy/transform/nesting graphs and all model/tool/UI/log/trace/exception/error sinks; only trusted Authorization transport may emit the complete bearer.
    - **Validates: Requirements 12.1–12.14, 14.30–14.31**

  - [x] 11.3 Write the property test for lifetime and conditional source proof
    - **Property 14: Approved lifetime and conditional source proof fail closed without weakening unconditional controls**
    - Generate approval/lifetime states, current times, source-proof evidence/outcomes, MCP requests, API source paths, and protected operations.
    - Require exact documented/active lifetime equality without an invented bound; treat `allowedWorkloadConfiguration` as candidate-only; keep MCP JWT/cross-lane and API source controls unconditional.
    - **Validates: Requirements 13.2–13.16, 14.32–14.36**

  - [x] 11.4 Write the property test for correlation and operational audit evidence
    - **Property 15: Correlation and audit evidence are operational, unchanged, and non-secret**
    - Generate invocation and selected-lane door sequences; require one unchanged correlation ID with safe door/lane/subject/tenant/outcome fields and no cryptographic actor-chain claim.
    - **Validates: Requirements 13.17–13.22, 14.37–14.38**

  - [x] 11.5 Add the two-lane managed-door authorization matrix
    - Exercise valid, tampered, expired, wrong-client, wrong-type, missing-scope, and other-lane access tokens at Agent Runtime, Gateway, and MCP Runtime in both directions; assert rejection before application sentinels.
    - Verify each deployed managed door has only its same-lane discovery URL and local policy.
    - _Requirements: 5.1–5.6, 6.1–6.8, 10.1, 13.14, 14.13–14.16, 14.19, 14.36_

  - [x] 11.6 Add per-lane Gateway HTTP MCP protocol proof tests
    - Through each target, verify initialize, direct `tools/list`, predefined non-mutating `tools/call`, complete ordered streaming, and other-lane rejection before candidate activation.
    - Inspect exact Runtime invocation URL and `JWT_PASSTHROUGH`; do not perform adjacent managed-service bearer-byte comparison.
    - _Requirements: 9.1–9.17, 14.24–14.25_

  - [x] 11.7 Add shared API boundary and failure-path integration tests
    - From both MCP lanes, verify same-bearer API calls, exact issuer selection, independent verification, read/write scope, subject/tenant authorization, approved source paths, RLS/isolation, and zero MCP fallback when API is unavailable.
    - _Requirements: 5.7–5.13, 6.4–6.8, 7.1–7.19, 8.1–8.14, 13.15–13.16, 14.17–14.23, 14.36_

  - [x] 11.8 Add browser renewal, expiry, and conversation integration tests
    - Verify access-token renewal remains in the selected pool, refresh material never leaves the browser, expiry ends one invocation, mutating operations are not replayed, identity changes clear state, and late events cannot mutate Conversation.
    - _Requirements: 3.9–3.19, 10.1–10.12, 11.1–11.13, 14.11, 14.28–14.29_

  - [x] 11.9 Add end-to-end forbidden-path and sink-sanitization sentinels
    - Assert zero M2M, exchange/OBO, OAuth-provider, context-token, workload-token, downstream refresh, caller tenant-header, direct datastore, or extra credential paths.
    - Inject provenance-tagged sentinels through model, tool, UI, telemetry, exception, and error paths and verify complete omission/redaction while trusted code-owned Authorization forwarding stays unchanged.
    - _Requirements: 3.16–3.19, 4.7–4.15, 8.12–8.14, 10.9–10.12, 12.1–12.14, 14.27, 14.30–14.31_

  - [x] 11.10 Add lane-local migration, rollback, and security-posture verification
    - Force target capability, protocol, cross-lane, and post-activation failures in each lane; verify affected-lane restoration and byte/state equality for the unaffected lane.
    - Verify machine-readable evidence records the approved/active lifetimes, per-lane shared-token blast radius, no hop-specific audience separation, conditional source-signal result, operational-not-cryptographic actor evidence, and audit ownership boundary.
    - _Requirements: 6.12, 9.9, 9.15–9.19, 13.1–13.14, 13.20–13.22, 14.26, 14.32–14.38_

- [x] 12. Final checkpoint — validate the complete implementation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Deploy Route C through gated two-lane cutover
  - [x] 13.1 Perform read-only deployment inventory and prerequisite verification
    - Inventory AgentCore Runtimes, Gateways, targets, qualifiers, routes, and authorizers without issuing any mutating API call; identify the existing `dynamic-skills-system` resources as protected and unavailable for Route C reuse or modification.
    - Inventory Cognito user pools, app clients, feature plans, and active PreTokenGeneration trigger configuration; verify whether exactly two intended tenant pools exist and whether each active trigger is `V2_0` and invokes the expected access-token customizer.
    - Verify configured foundation-model access, locate and validate `registry_output.json`, and discover the current Sage API deployment endpoint and approved source-control state. Treat a missing or invalid `registry_output.json` as a blocking failure.
    - Record the current shared/legacy topology, M2M and OAuth dependencies, exposed-secret references without reading or reproducing secret values, and independent rollback topology for each lane.
    - Produce a machine-readable, read-only preflight report and stop on every cardinality, access, evidence, or discovery mismatch.
    - _Requirements: 1.1–1.15, 2.17–2.19, 5.1–5.6, 8.1–8.2, 9.2–9.9, 13.2–13.16, 14.1–14.4, 14.9, 14.13, 14.24, 14.32–14.36_

  - [-] 13.2 Collect and approve every undiscoverable deployment value
    - Collect the exact Tenant A and Tenant B pool, client, issuer, discovery URL, tenant claim, lane endpoint/name, Runtime/Gateway/MCP identifiers, qualifier, scope, token-lifetime approval, Sage API source path, model, Region, frontend, rollback-window, and operational owner values that read-only discovery cannot establish.
    - Require customer or operator approval for every collected value, including exact active/documented token-lifetime equality and the source-signal classification; leave missing or disputed fields unresolved rather than inventing defaults, deriving guesses, or reusing shared/legacy values.
    - Define exactly two Cognito pools, two Agent Runtimes, two Gateways, two MCP Runtimes, one shared Sage API, and six same-lane managed JWT authorizers as the only approved Route C resource cardinality.
    - Create an approved secret-rotation plan that identifies the exposed legacy M2M credential by non-secret resource reference, defines rollback-safe rotation/revocation timing, and prohibits the secret value from command output, files, logs, prompts, or task results.
    - _Requirements: 1.1–1.10, 2.4–2.5, 2.17–2.19, 5.1–5.6, 6.1–6.12, 8.1–8.2, 13.1–13.16, 14.1–14.4, 14.13, 14.19, 14.32–14.36_

  - [x] 13.3 Create and validate the approved Route C deployment manifest
    - Only after Task 13.2 approval, create deployment-owned validation/deployment helpers and `scripts/identity_deployment.json` from the approved values; do not import undiscovered defaults or legacy M2M/OAuth/shared-topology bindings.
    - Require `registry_output.json`, preserve `dynamic-skills-system` unchanged, and fail validation when either artifact or any approved lane value is missing, ambiguous, stale, cross-lane, or inconsistent.
    - Encode exactly two immutable lane records, six same-lane authorizers, one shared Sage API, the original user-access-JWT path, HTTP MCP `JWT_PASSTHROUGH` targets, inactive candidate resources, per-lane rollback snapshots, approved token lifetimes, source restrictions, and correlation evidence.
    - Add schema and dry-run tests proving exact cardinality, same-lane bindings, no secret material, no shared/legacy topology reuse, no M2M/OAuth credential provider, and zero AWS mutation during validation.
    - _Requirements: 1.1–1.16, 4.1–4.16, 5.1–5.16, 6.1–6.12, 8.1–8.4, 9.1–9.9, 13.2–13.22, 14.1–14.6, 14.12–14.19, 14.24, 14.27, 14.30–14.38_

  - [x] 13.4 Build and dry-run a staged, fail-closed deployment procedure
    - Implement a deployment procedure that resolves circular dependencies by creating or updating the shared Sage API, MCP Runtimes, Gateways/targets, and Agent Runtimes in inactive stages, then patches exact discovered identifiers without routing user traffic until both lanes pass every proof gate.
    - Separate read-only inspection and local file generation from mutation commands; require dry-run output to enumerate intended changes, protected resources, rollback actions, and zero secret values.
    - Add guards that reject any semantic target, Runtime target, shared Gateway/Runtime, legacy M2M token path, OAuth provider, token exchange, context/workload token, missing qualifier, non-MCP target, non-`JWT_PASSTHROUGH` target, or mutation of `dynamic-skills-system`.
    - Make every stage stop on failure, preserve both rollback topologies, restore only an affected staged lane when safe, and prohibit either lane's traffic activation or frontend deployment until both lanes pass proof.
    - Add automated dry-run tests for circular-dependency patch order, failed-stage rollback, unaffected-lane noninterference, and absence of AWS mutations before human authorization.
    - _Requirements: 4.2–4.16, 5.1–5.16, 6.1–6.12, 8.3–8.14, 9.1–9.19, 10.1–10.12, 13.8–13.22, 14.12–14.27, 14.32–14.38_

  - [~] 13.5 Freeze approved inputs and record explicit human mutation authorization
    - Re-run the read-only preflight, manifest validation, dry-run diff, protected-resource checks, `registry_output.json` requirement, rollback verification, and secret-safe output checks against current AWS state.
    - Stop and obtain explicit human confirmation immediately before the first AWS-mutating command; record only a non-secret approval reference and timestamp in deployment run state.
    - Require every mutation command to verify the approval reference, frozen manifest digest, current preflight digest, and unexpired operator session; any mismatch must return to read-only discovery and require new approval.
    - _Requirements: 1.11–1.16, 8.10–8.14, 9.15–9.19, 13.2–13.16, 14.5–14.6, 14.23–14.27, 14.32–14.36_

  - [~] 13.6 Cloud mutation — deploy the single shared Sage API boundary and source restrictions
    - Deploy or update exactly one shared Sage API from the frozen manifest, with exactly two issuer-map entries, independent JWT validation, read/write scopes, subject and tenant authorization, RLS/non-relational isolation, and unconditional approved source restrictions.
    - Keep the API unavailable to Route C traffic until configuration inspection confirms the exact issuer map, validation order, source paths, safe errors, and zero direct Agent/MCP datastore fallback.
    - Preserve the prior API configuration for rollback and stop without continuing to Cognito or lane resources if deployment or inspection fails.
    - _Requirements: 5.7–5.13, 6.4–6.8, 8.1–8.14, 13.15–13.16, 14.17–14.23, 14.36_

  - [~] 13.7 Cloud mutation — configure exactly two Cognito access-token issuers
    - Configure only the approved Tenant A and Tenant B pools with their public clients, trusted assignment sources, canonical tenant claim, authorized Route C scopes, active `V2_0` access-token customizers, and approved token lifetimes.
    - Verify active feature-plan support, active PreTokenGeneration `V2_0` bindings, protected-claim preservation, exact final scope sets, expected tenant claims, and documented/active lifetime equality in both pools before continuing.
    - Create no shared agent-facing pool, federation, M2M pool/client, fallback token, or unapproved lifetime; restore the affected pool configuration and stop if either pool fails, leaving Route C traffic disabled for both lanes.
    - _Requirements: 1.2, 1.4–1.6, 2.1–2.21, 6.9, 13.2–13.6, 14.7–14.9, 14.32_

  - [~] 13.8 Cloud mutation — deploy two inactive Sage MCP Runtimes
    - Deploy exactly two MCP Runtimes from the shared Sage MCP code, one per lane, while requiring `registry_output.json` and preserving `dynamic-skills-system` unchanged.
    - Configure one same-lane JWT authorizer per MCP Runtime with the approved issuer discovery URL, trusted client set, `token_use=access`, `sage-mcp/invoke`, Authorization/correlation header allowlists, expected lane tenant, shared Sage API endpoint, and unconditional API source path controls.
    - Apply a same-lane Gateway source restriction only when the approved Source Signal Proof Record proves the mechanism; otherwise record the control unavailable without weakening issuer/client/type/scope/cross-lane enforcement.
    - Keep both MCP Runtimes inactive from user traffic, retain per-lane rollback state, and stop on either lane's deployment or inspection failure.
    - _Requirements: 1.3, 1.7–1.10, 4.3, 4.6–4.8, 5.1–5.6, 5.16, 6.3, 8.3–8.4, 13.8–13.16, 14.3, 14.12–14.16, 14.33–14.36_

  - [~] 13.9 Cloud mutation — deploy two Gateways and HTTP MCP passthrough targets
    - Deploy exactly two lane-specific Gateways with one same-lane JWT authorizer each and create exactly one target-specific HTTP passthrough target per lane using `targetConfiguration.http.passthrough.protocolType: MCP` and `credentialProviderType: JWT_PASSTHROUGH`.
    - Patch each target only to the exact URL composed from the deployed same-lane MCP Runtime ARN, Region, and qualifier; retain the original user JWT and correlation ID and configure zero OAuth providers or replacement credentials.
    - Reuse neither `dynamic-skills-system` nor any semantic/shared/legacy M2M target; keep candidate routes inactive, preserve prior lane targets/routes, and stop both-lane activation if either target fails inspection.
    - _Requirements: 1.3, 1.7–1.10, 4.5, 4.7–4.15, 5.1–5.6, 6.2, 9.1–9.19, 13.8–13.14, 14.13–14.16, 14.24–14.27, 14.33–14.36_

  - [~] 13.10 Cloud mutation — deploy two inactive Agent Runtimes
    - Deploy exactly two Agent Runtimes from the shared Agent code with one same-lane JWT authorizer each, lane-specific Gateway target URL, configured model, original bearer forwarding, correlation propagation, and no M2M/OAuth/exchange/context/workload/tenant-header path.
    - Patch circular Runtime/Gateway identifiers only from inspected deployed outputs and the frozen manifest; configure no caller-extensible endpoint or issuer map.
    - Keep both Agent Runtimes unavailable to frontend traffic, preserve prior Agent/Gateway routes, and stop before proof or activation if either lane fails deployment or inspection.
    - _Requirements: 1.3, 1.7–1.10, 4.2–4.4, 4.7–4.16, 5.1–5.6, 5.15, 6.1, 10.2–10.4, 13.17–13.19, 14.3, 14.12–14.16, 14.27, 14.37_

  - [~] 13.11 Verify both inactive lanes before any traffic activation
    - Inspect deployed state for exactly two Cognito pools, two Agent Runtimes, two Gateways, two HTTP MCP `JWT_PASSTHROUGH` targets, two MCP Runtimes, one shared Sage API, and six same-lane JWT authorizers; compare every value with the frozen manifest.
    - For each lane, run MCP initialize, direct `tools/list`, predefined non-mutating `tools/call`, complete ordered streaming, API authorization/isolation, source-control, correlation, and safe-error checks through the candidate route.
    - Verify both-direction cross-lane rejection at Agent Runtime, Gateway, and MCP Runtime; exact bearer preservation only at Frontend-emission simulation, Agent Application, and Sage MCP code-owned boundaries; and configured/behavioral passthrough at the managed Gateway boundary.
    - Run forbidden-path sentinels for legacy M2M, OAuth, exchange/OBO, context/workload token, downstream refresh, caller tenant header, direct datastore, secret disclosure, shared topology, and `dynamic-skills-system` mutation.
    - Exercise candidate failure, rollback restoration, and unaffected-lane noninterference checks; retain both rollback topologies, keep traffic disabled, and stop on any failed gate.
    - _Requirements: 4.1–4.16, 5.1–5.16, 6.1–6.12, 8.1–8.14, 9.3–9.19, 10.1–10.12, 13.8–13.22, 14.12–14.31, 14.33–14.38_

  - [~] 13.12 Cloud mutation — perform controlled two-lane cutover and legacy secret containment
    - Only after every Task 13.11 check passes for both lanes, apply the staged active configuration patches for both lanes while keeping the frontend on the prior topology until both active paths re-pass the proof gate.
    - Execute the approved rollback-safe rotation/revocation and removal plan for the exposed legacy M2M secret by non-secret resource reference; do not read, print, copy, persist, or reproduce the secret value, and verify that no Route C or retained rollback configuration uses the legacy M2M/OAuth credential path.
    - Require post-patch proof for both lanes before marking either lane active; if either lane or secret-containment check fails, stop, restore the verified rollback topology as defined by the approved plan, and leave frontend routing unchanged.
    - _Requirements: 4.2, 4.5, 4.9–4.15, 6.10, 9.15–9.19, 13.1–13.14, 14.24–14.27, 14.32–14.36_

  - [~] 13.13 Cloud mutation — deploy the trusted two-lane frontend configuration last
    - Deploy or update the frontend only after both active lane paths pass Task 13.12 proof, using exactly two immutable lane records, access tokens, lane-specific endpoints, browser-only renewal, and conversation/session binding.
    - Remove active shared-pool, static bearer, tenant-header, legacy M2M, OAuth, and caller-extensible fallback configuration without exposing the rotated legacy secret or changing `dynamic-skills-system`.
    - Verify the deployed frontend selects only the approved lane endpoint, sends the original user access JWT, retains renewal material only in the browser, and cannot activate only one lane; restore prior frontend routing and stop on failure.
    - _Requirements: 1.1–1.10, 2.6, 3.1–3.19, 4.1–4.2, 4.7, 10.5–10.12, 11.1–11.13, 14.10–14.12, 14.28–14.29_

  - [~] 13.14 Run final deployed verification and retain rollback topology
    - Re-run deployed configuration inspection, same-lane protocol checks, both-direction cross-lane rejection, Sage API source/authorization/isolation checks, code-owned bearer-preservation checks, forbidden-path checks, source-signal classification, correlation/audit checks, and rollback/noninterference checks against the live frontend path.
    - Run final smoke tests for Tenant A and Tenant B authentication, browser renewal, non-mutating business-data retrieval, ordered streaming, expiry termination, conversation isolation, safe errors, and zero automatic write replay.
    - Confirm `dynamic-skills-system` and `registry_output.json` remain intact, all six authorizers remain same-lane, HTTP MCP `JWT_PASSTHROUGH` remains the only Gateway target credential mode, the legacy exposed secret is contained without disclosure, and no partial lane activation exists.
    - Retain both verified rollback topologies through the approved rollback window; stop and execute the affected approved rollback without continuing or deleting rollback resources on any failed final gate.
    - _Requirements: 1.1–1.16, 2.1–2.21, 4.1–4.16, 5.1–5.16, 6.1–6.12, 8.1–8.14, 9.1–9.19, 10.1–10.12, 13.1–13.22, 14.1–14.38_

- [x] 14. Ponytail simplification
  - [x] 14.1 Reconcile the simplification plan with security requirements and deployment gates
    - Update the requirements and design before deleting code so they specify observable security behavior rather than mandating particular wrappers, state models, serializers, callback layers, or test shapes.
    - Preserve the hard constraints: exactly two tenant lanes, independently validated access tokens, exact same-bearer forwarding at code-owned boundaries, fail-closed authorization and isolation, browser-only renewal, conversation isolation, stable safe errors, and no fallback credential or datastore path.
    - Mark superseded implementation-prescriptive requirements explicitly and rerun Tasks 13.3 through 13.5 after simplification because code, manifest, dry-run, or preflight digests may change.
    - Block Task 13.6 and every later cloud mutation until Task 14 is complete and the refreshed Task 13.5 authorization is recorded.

  - [x] 14.2 Remove test-only Route C configuration and proof machinery
    - Delete topology transition, configuration-store, protocol-proof, and security-posture abstractions that have no production caller; retain only lane records, authorizer rendering, source evaluation, target evidence, and deployed behavior checks.
    - Replace tests of deleted models with focused assertions against rendered deployment state and observable rollback/proof behavior.
    - Keep lane-local rollback and both-lane proof gates in the deployment path rather than representing them only with in-memory test objects.

  - [x] 14.3 Collapse the shared Sage API into the smallest deployable boundary
    - Add the actual HTTP entrypoint for the product and claim reads; keep independent JWT verification, exact issuer selection, the fixed read scope, source allowlist, tenant authorization, audit fields, and tenant-derived isolation directly in that boundary. If a mutating endpoint is added later, it must add its own write authorization and focused tests.
    - Remove callback-based authorization plumbing, repository layers, write-operation scaffolding, and generic extension points that have only one implementation or no deployed caller.
    - Keep demo data owned by the Sage API and preserve zero direct or fallback data access from Agent or MCP code.

  - [x] 14.4 Simplify Agent and MCP transport code around public SDK and JSON boundaries
    - Remove the recursive MCP result schema projector because the Sage API client already returns JSON values; validate only the response shape required by each tool.
    - Replace the private-method `MCPClient` subclass with the public client path unless a runnable regression proves the SDK cannot preserve expiry termination and stable failure behavior.
    - Remove serializer aliases with no production caller while retaining strict bearer parsing, the sole Authorization transport boundary, correlation propagation, complete log redaction, and safe public errors.

  - [x] 14.5 Simplify frontend session, event, and credential handling
    - Capture one immutable invocation binding per request instead of cloning it onto every stream event; keep late-event rejection by checking the captured binding before state mutation.
    - Use `sessionId` as the conversation-reset dependency because login changes it and same-identity renewal preserves it; continue clearing conversation on identity or lane change.
    - Validate incoming stream fields once and stop re-sanitizing application-owned message state on every event.
    - Remove unused credential-provenance variants and synthetic `derive()` behavior while keeping the access token outside display props, serialized payloads, and retained conversation content.

  - [x] 14.6 Prune tests to observable invariants
    - Delete tests whose only purpose is exercising removed abstractions, serializer aliases, provenance variants, or state models.
    - Retain one focused regression or property test for each real trust-boundary invariant: two-lane isolation, token validation, same-bearer forwarding, source authorization, tenant isolation, expiry termination, no write replay, conversation isolation, safe errors, and rollback noninterference.
    - Prefer end-to-end boundary checks over mirrored implementation fixtures and keep the smallest suite that fails when behavior regresses.

  - [x] 14.7 Remove local artifacts and run the simplification checkpoint
    - Exclude `.hypothesis/`, `.pi/`, `.serena/`, editor bundles, generated extension packages, and other machine-local state from the change set; add only narrowly scoped ignore entries that are safe for all contributors.
    - Run backend tests, frontend tests, frontend build/type checking, and dry-run deployment validation; fix failures without restoring deleted abstractions.
    - Record the final line-count reduction and confirm every preserved security invariant before returning to Task 13.5.

## Notes

- No task is optional unless a later approved requirements amendment explicitly removes it; Task 14 may remove implementation-prescriptive work only after preserving the corresponding observable security behavior.
- Reuse the existing Agent, FastMCP tools, React components, Cognito client, deployment scripts, pytest, and Hypothesis structure before adding files or dependencies.
- The implementation remains fixed to exactly two tenant pools and lanes; dynamic tenancy and a third tenant are excluded.
- Bearer equality is asserted only at code-owned Frontend, Agent Application, and Sage MCP boundaries. Managed Gateway-to-MCP Runtime behavior is verified through configuration and authorization outcomes.
- A same-lane MCP Runtime source restriction is conditional on the Source Signal Proof Gate. `allowedWorkloadConfiguration` is candidate-only; lane JWT/client/type/scope/cross-lane controls and Sage API Approved Source Paths remain unconditional.
- No numeric access-token lifetime is introduced by this plan; active values must exactly match customer-approved evidence.
- Task 13.1 through Task 13.5 are read-only discovery or local file-preparation gates. Task 13.6 through Task 13.14 are cloud-mutation or deployed-verification tasks and cannot begin without Task 14 completion and a refreshed explicit Task 13.5 human authorization record.
- `dynamic-skills-system` is protected from Route C mutation or reuse, and a current valid `registry_output.json` is a mandatory deployment input.
- Every Task 13 deployment item is required. Any failed gate stops the sequence, prevents partial activation, and retains or restores the approved rollback topology.

## As-Deployed POC Status

Where the deployed proof of concept diverges from this plan. Architecture and
security deviations are recorded in `design.md` under "As-Deployed POC Deviations".

- **Task 13.5 authorization was recorded after the fact.** The plan requires freezing the manifest digest and recording explicit human mutation authorization *before* the first AWS mutation. Cognito pools, the customizer Lambdas, the Sage API, and both Gateways were created before any such record existed. The retrospective record is kept locally and is explicitly marked `recordType: RETROSPECTIVE`; it is not committed because it carries account identifiers.
- **Requirements 9.9 and 9.16–9.19 and Tasks 13.12/13.14 have nothing to roll back to.** The prior stack was deleted first at the operator's explicit instruction, so `rollbackTopology` holds `none-*` placeholders. The new stack is the only stack, and the approved rollback window cannot be honored for this deployment.
- **`deploy_user_pool.py` has not run.** The `sage-*` resource servers therefore do not exist in either new pool and there is no `user_pool_output.json`. The four Sage scopes still reach access tokens because the `V2_0` customizer injects them, which is why nothing appears broken. Running it requires `<LANE>_AGENT_RUNTIME_ENDPOINT`, so it must follow the Agent Runtime deployment.
- **Unrelated resources remain live in the account.** Four `emily_*`/`emily-*` resources were never cleaned up. All such references were removed from this repository; the AWS resources are outside the Route C teardown scope.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.1", "6.1", "9.1", "10.1"] },
    { "id": 3, "tasks": ["2.2", "5.1", "6.2", "7.1", "10.4"] },
    { "id": 4, "tasks": ["2.3", "2.4", "3.1", "5.2", "6.3", "6.4", "7.2", "7.3", "10.2"] },
    { "id": 5, "tasks": ["3.2", "5.3", "7.4", "7.5", "9.2", "10.3", "10.5"] },
    { "id": 6, "tasks": ["3.3", "3.5", "9.3", "9.4", "10.6", "10.7"] },
    { "id": 7, "tasks": ["3.4", "3.6", "3.7", "9.5", "11.1", "11.3", "11.4", "11.5", "11.6", "11.7", "11.10"] },
    { "id": 8, "tasks": ["3.8", "11.2", "11.8", "11.9"] },
    { "id": 9, "tasks": ["13.1"] },
    { "id": 10, "tasks": ["13.2"] },
    { "id": 11, "tasks": ["13.3"] },
    { "id": 12, "tasks": ["13.4"] },
    { "id": 13, "tasks": ["14.1"] },
    { "id": 14, "tasks": ["14.2", "14.3", "14.5"] },
    { "id": 15, "tasks": ["14.4"] },
    { "id": 16, "tasks": ["14.6"] },
    { "id": 17, "tasks": ["14.7"] },
    { "id": 18, "tasks": ["13.5"] },
    { "id": 19, "tasks": ["13.6"] },
    { "id": 20, "tasks": ["13.7"] },
    { "id": 21, "tasks": ["13.8"] },
    { "id": 22, "tasks": ["13.9"] },
    { "id": 23, "tasks": ["13.10"] },
    { "id": 24, "tasks": ["13.11"] },
    { "id": 25, "tasks": ["13.12"] },
    { "id": 26, "tasks": ["13.13"] },
    { "id": 27, "tasks": ["13.14"] }
  ]
}
```
