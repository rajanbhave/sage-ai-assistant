# Sage on AgentCore Runtime Instances (re:Invent 2026 demo)

Runs Sage's two tenant agents on **AgentCore Runtime Instances** (EC2 that AgentCore launches in
our account) instead of microVMs, so the DoiT Attribute EC2 sensor can measure Bedrock cost per
agent and per tenant. The existing microVM lanes, Gateways, MCP runtimes and Sage API are reused
and left running.

| Piece | Where |
|---|---|
| VPC with NAT, IAM roles, sensor installer Lambda on a 1-minute schedule | `stack.yaml` (CloudFormation) |
| Sensor installer: finds AgentCore instances, installs the sensor over SSM | `sensor_installer.py` (deployed by `deploy_instances.py` with a current boto3) |
| One capacity provider per tenant, two new agent runtimes cloned from the microVM ones; `--rebuild` repackages the code into the stack's artifact bucket and sets `SAGE_TENANT_LABEL` per lane | `deploy_instances.py` |
| Every Bedrock call carries `requestMetadata: {x-tenant-id: bluepine|oakhaven}` | `agent/agent.py` (`TenantTaggedBedrockModel`) |
| Ordered teardown | `teardown.py` |
| Pinned-session demo traffic (Bluepine 3:1 Oakhaven) | `traffic.py` |
| Frontend: pinned session per lane, session header on every call | `frontend/src/lib/auth/cognito.ts`, `frontend/src/lib/agentcore-client/client.ts` |

Workloads in Attribute: `sage-agent-bluepine` (Tenant_A) and `sage-agent-oakhaven` (Tenant_B).

What we learned deploying it (23 Nov 2026):
- The toolkit's code bucket expires every object after 7 days (even rebuilt ones); the zip now lives in the stack's
  `ArtifactBucket` under a content-addressed key.
- AgentCore managed instances send no EC2 state-change events to the account bus and are hidden unless
  `DescribeInstances` sets `IncludeManagedResources`, so the installer polls every minute.
- DNS on the instances returns IPv6 first, but the subnets have no IPv6 route, so AWS calls hung until their
  signatures expired. The installer makes glibc prefer IPv4 (`/etc/gai.conf`) before anything else.
- On Instances the agent's startup call to the skills registry is denied although the role allows it
  (it worked on microVMs); the agent falls back to the bundled `skills/`.
- `StopRuntimeSession` needs the runtime's JWT; use `bedrock-agentcore delete-capacity-provider-session` instead.
- A CloudFormation stack update resets the installer to its stub; re-run `deploy_instances.py` afterwards.

## 0. Prerequisites (Rajan)

```bash
aws sso login                     # account 434801484416, us-east-1
export AWS_REGION=us-east-1
# Attribute sensor token: typed at a hidden prompt, never echoed or stored in shell history
read -rs "TOKEN?Attribute sensor token: " && \
  aws secretsmanager create-secret --name sage-reinvent/attribute-sensor-token \
    --secret-string "{\"token\":\"$TOKEN\"}" && unset TOKEN
```

Copy the local, git-ignored deployment config from the deployed checkout:

```bash
cp ../sage-ai-assistant-phase2/scripts/{identity_deployment,registry_output,gateway_output,sage_api_output,pre_token_lambda_output,tenant_pool_bootstrap,user_pool_output,demo_credentials.local}.json scripts/ 2>/dev/null
cp ../sage-ai-assistant-phase2/frontend/.env.local frontend/.env.local
```

## 1. Renamed tenants (Bluepine Insurance, Oakhaven Mutual)

1. Redeploy the Sage API so the mock data shows the new names: `uv run python scripts/deploy_sage_api.py` (render first if the script supports it).
2. Cognito usernames cannot be renamed. Create `bluepine-user` and `oakhaven-user` with
   `scripts/bootstrap_tenant_pool.py create --lane ... --username ... --confirm`
   (password from `TENANT_A_DEMO_PASSWORD` / `TENANT_B_DEMO_PASSWORD`).
3. The pre-token customizer grants scopes per subject (`sub`). Redeploy it per lane with both the
   old and the new subject: `scripts/deploy_pre_token_lambda.py ... --subject <old-sub> --subject <new-sub>` (`--render` first).
4. Update `scripts/demo_credentials.local.json` to the new usernames.

## 2. Infrastructure

```bash
aws cloudformation deploy --stack-name sage-inst --template-file infra/instances/stack.yaml \
  --capabilities CAPABILITY_IAM
uv run python -m infra.instances.deploy_instances --dry-run   # inspect both requests
uv run python -m infra.instances.deploy_instances             # writes instances_output.json
```

Put the printed `VITE_TENANT_{A,B}_AGENT_RUNTIME_ENDPOINT` values into `frontend/.env.local`.

## 3. Go/no-go (Tuesday, before any volume)

```bash
uv run python -m infra.instances.traffic --once
```

Prints `VITE_TENANT_{A,B}_RUNTIME_SESSION_ID`; add them to `frontend/.env.local` so the browser
uses the same warm instance. The first call boots an instance and can take minutes. Then check:

1. **JWT authorizer works on Instances**: both calls return 200; a Tenant_A token on the Tenant_B URL returns 401/403 (UI cross-lane probe).
2. **Sensor installed**: `aws logs tail /aws/lambda/sage-inst-sensor-installer --since 1h` shows `started`, and
   `aws ssm list-command-invocations --details --max-items 4` shows an "Attribute sensor" command `Success` with `zprobe` active.
3. **Attribute sees Bedrock**: within about 2 hours, workloads `sage-agent-bluepine` / `sage-agent-oakhaven` show Bedrock tokens.

If 3 fails: switch to the fallback kiosk cut (plan Q14) and ask Liad about the September
"sensor running, no Bedrock metrics" thread on AgentCore.

## 4. Traffic

```bash
uv run python -m infra.instances.traffic --hours 48 --per-hour 40
```

Instances stop after 15 idle minutes, so keep traffic running while the cost story needs data.
Each log line has `outcome`: `ok` only when the agent streamed an answer; `stream_error_<code>`, `no_answer` or `http_<status>` otherwise.

## 5. Teardown (Friday 4 December)

```bash
uv run python -m infra.instances.teardown            # prints what will be deleted
uv run python -m infra.instances.teardown --confirm  # deletes, waiting at each step
```

Order: stop traffic, delete runtimes and wait, delete capacity providers and wait until their managed
instances are gone, empty the artifact bucket, delete the stack (VPC, NAT, EIP, roles, installer) and wait,
delete the three log groups, delete the sensor-token secret. It then lists the manual follow-ups
(frontend env, demo users and scope grants, token rotation, `terraform destroy` for the Attribute role).
