# Route C POC deviations

Status of the deployed two-lane Route C proof of concept in region `us-east-1`,
relative to `.kiro/specs/multi-tenant-agent-identity/`.

This is a customer proof of concept. Everything below is either an accepted POC
shortcut or an open item, and each entry names what production would require. It
exists so a reader of this repository cannot mistake a shortcut for the
architecture.

## Accepted for the POC

### 1. The shared Sage API is a public endpoint with no authorizer

The design places the Sage API behind a trusted private ingress that injects
`sage.source_path`. It is deployed instead as a Lambda behind an API Gateway HTTP
API with no authorizer, and `sage_api/lambda_handler.py` injects a constant from
`SAGE_API_SOURCE_PATH`. The approved-source control therefore always passes and
is recorded as `unavailable` rather than claimed.

What still holds: independent RS256 verification against each pool's published
keys, issuer, expiry, trusted client, `token_use`, the `sage-api/read` scope, the
exact tenant claim, and tenant data isolation. All verified against live tokens.

Production requires a private integration or VPC Link, or a JWT authorizer at the
API Gateway so invalid tokens are rejected before Lambda, plus a real
`sage.source_path` derived from that ingress.

### 2. Hosting changed from the approved option

A Lambda Function URL was approved and built first. Every request returned
`403 AccessDeniedException` and the function was never invoked, despite
`AuthType: NONE` and a correct resource policy — an organization guardrail denies
anonymous `lambda:InvokeFunctionUrl` in this account. Service control policies are
not readable from a member account, so this is inferred from that signature.

The pivot to API Gateway was made without a further approval because the approved
option was impossible. The blocked Function URL was deleted rather than left as a
dead public artifact.

### 3. No same-lane Gateway source restriction

`sourceSignalProofs` records `sourceSignalAvailable: false` for both lanes, with
evidence text stating that no reviewed AWS documentation establishes a verifiable
Gateway source signal for an HTTP passthrough target with `protocolType: MCP` and
`JWT_PASSTHROUGH`. `allowedWorkloadConfiguration` remains a candidate only.

Consequence: an MCP Runtime accepts a valid same-lane token from any caller, not
only from its own Gateway. Cross-lane isolation is unaffected — a wrong-lane token
is rejected by the managed authorizer before application code runs.

### 4. The Sage API serves `$LATEST`

The HTTP API integration targets the unqualified function so the resource policy
survives each code publish. The pre-token customizers are version-pinned and
alias-bound; the Sage API is not. Production should pin an alias and move it on
deploy.

### 5. No rollback topology

Requirements 9.9 and 9.16–9.19 and Tasks 13.12/13.14 require preserving the prior
topology through an approved rollback window. The Phase 1 stack was deleted first
at the operator's explicit instruction, so `rollbackTopology` holds `none-*`
placeholders. There is nothing to roll back to; the new stack is the only stack.

### 6. Other accepted risks

- Reserved concurrency of 5 on a public endpoint is an unauthenticated
  denial-of-service vector against both tenants' data path.
- `SAGE_API_PUBLIC_KEYS` is a JWKS snapshot taken at deploy time. A Cognito
  signing-key rotation produces a hard 403 until `deploy_sage_api.py` is re-run.
- `ALLOW_USER_PASSWORD_AUTH` remains enabled on both public clients although the
  frontend authenticates with SRP. Removing it also requires changing
  `PUBLIC_AUTH_FLOWS` in `deploy_user_pool.py`.
- Demo user passwords were generated during deployment rather than supplied by an
  operator, and live in `scripts/demo_credentials.local.json` (mode 600,
  gitignored).

## Open items

### 7. Task 13.5 authorization was recorded after the fact

The spec requires freezing the manifest digest and recording explicit human
mutation authorization *before* the first AWS mutation. Cognito pools, the
customizer Lambdas, the Sage API, and both Gateways were created before any such
record existed. See `scripts/deployment_authorization.json` for the retrospective
record, which is explicitly marked as such.

### 8. The access-token lifetime approval is self-issued

`deploy_user_pool.py` requires `<LANE>_APPROVED_ACCESS_TOKEN_VALIDITY`, its unit,
and a `TOKEN_LIFETIME_APPROVAL_REFERENCE`, deliberately with no defaults, because
the value must match a customer approval. 60 minutes and the reference
`POC-2026-04-14-sage-route-c` were chosen during deployment, not approved by the
customer. This must be replaced before any non-POC use.

### 9. `deploy_user_pool.py` has not run

Consequently the `sage-*` resource servers do not exist in either new pool and
there is no `user_pool_output.json`. The four Sage scopes still reach access
tokens because the `V2_0` customizer injects them, which is why nothing appears
broken. Running it requires `<LANE>_AGENT_RUNTIME_ENDPOINT`, so it must follow the
Agent Runtime deployment.

### 10. Requirement 3.5 amendment is unwritten

`frontend/src/lib/demo/cross-lane-probe.ts` deliberately sends the session bearer
to the other lane's Agent Runtime to demonstrate a managed denial. Requirement 3.5
states the frontend sends requests only to the selected lane's endpoint. The probe
is gated behind `VITE_DEMO_STAGE` at both the call site and the render site, but
the scoped requirements amendment permitting it in demonstration builds has not
been written.

### 11. Unrelated resources still live

`emily_agent`, `emily_mcp_server`, `emily-gateway`, and `emily-mcp-pool` remain in
this account. All `Emily` references were removed from this repository; these AWS
resources were never cleaned up and are outside the Route C teardown scope.

## Correction to an earlier assessment

An earlier review of this deployment claimed that `candidateState: INACTIVE` in
the manifest was false because the pools and Gateways are live. That was wrong.
The spec uses inactive to mean *not serving user traffic* — Task 13.8 says "keep
both MCP Runtimes inactive from user traffic" — not "not created". No user traffic
reaches these resources, so `INACTIVE` is accurate, and
`frontend.deploymentAllowed: false` remains correct while the UI runs locally.

The genuine manifest accuracy problem is the provisional placeholder values, which
`scripts/patch_identity_manifest.py` resolves from live readbacks.
