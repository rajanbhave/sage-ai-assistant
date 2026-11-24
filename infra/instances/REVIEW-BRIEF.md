# Review brief: Sage on AgentCore Runtime Instances with DoiT Attribute

You are an independent reviewer. Validate that this setup is correct and will produce the desired
results. Do not trust the author's conclusions; check them against the code, AWS state and docs.

## Desired results (by Thu 26 Nov 2026, for a 60 s re:Invent kiosk video and a 3 Dec talk)

1. Two tenant agents (Bluepine Insurance = Tenant_A, Oakhaven Mutual = Tenant_B) run on **AgentCore
   Runtime Instances** (EC2 in our account via capacity providers), not microVMs.
2. Each tenant sees only its own data; a Tenant_A token sent to Tenant_B's runtime is rejected (401/403).
3. The DoiT Attribute EC2 sensor (`zprobe`) runs on every instance, reporting workloads
   `sage-agent-bluepine` and `sage-agent-oakhaven`, and captures the agents' **Amazon Bedrock** calls
   (model, tokens) so Attribute can show cost per agent and per tenant.
4. Scripted traffic (3:1 Bluepine:Oakhaven, one pinned runtime session per tenant) produces enough
   Bedrock usage for Attribute token counts within hours and dollar figures within 1 to 3 days.
5. The frontend (React, `frontend/`) can be screen-recorded against the Instances runtimes, including
   the cross-lane rejection probe, and shows no real insurer names (AXA and Allianz were renamed).
6. Everything can be torn down cleanly on 4 Dec.

## What to review

- `git diff` and untracked files on branch `feature/reinvent-agentcore-instances` (vs `feature/agentcore-identity-split`).
- `infra/instances/`: `stack.yaml` (CloudFormation), `deploy_instances.py`, `sensor_installer.py`,
  `traffic.py`, `README.md` (runbook, including "What we learned").
- `agent/agent.py` registry fallback to bundled `skills/`.
- Frontend: `frontend/src/lib/auth/cognito.ts` (pinned session ID), `frontend/src/lib/agentcore-client/client.ts`
  (`X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` header). Check whether the runtime's CORS / request-header
  handling will accept that header from a browser, and whether the frontend still works.
- The tenant rename: completeness, consistency of IDs (`BLP-MOT`, `OKH-MOT`), tests.
- Reference implementation for comparison: https://github.com/doitintl/attribute-agent-core (use `gh`).

## Live AWS state (read-only)

Account 434801484416, us-east-1, profile `434801484416-AdministratorAccess-SSO`. Resources: stack `sage-inst`,
capacity providers `sage_inst_cp_a/b`, runtimes `sage_agent_inst_a/b` (IDs in
`infra/instances/instances_output.json`), Lambda `sage-inst-sensor-installer`, secret
`sage-reinvent/attribute-sensor-token`. Instances are hidden unless `describe-instances --include-managed-resources`.
You may run read-only AWS calls (describe/get/list, CloudWatch metrics and logs, `ssm send-command` with
read-only shell commands such as `systemctl is-active zprobe` and `journalctl -u zprobe`).
A traffic generator is already running (`traffic_log.jsonl`).

Key question to settle with evidence: **is the sensor actually seeing Bedrock traffic from the agent process?**
Look at zprobe logs/config on an instance, the agent's process and Python build (statically linked OpenSSL
was a known issue; fixed in sensor 0.0.291+), the installed sensor version, and anything in the sensor that
indicates HTTP/Bedrock capture. Also check: does the agent call Bedrock via `bedrock-runtime` from the instance
(not from an AWS-managed component), and is tenant identity visible in that traffic (Attribute needs a tenant
identifier in runtime traffic, e.g. a header, JWT claim, or Bedrock `requestMetadata` in the body)?

## Hard rules

- **Do not change any AWS resource, IAM, secret or configuration.** No create/update/delete/put calls, no
  restarting services, no stopping the traffic generator (pid in `ps`).
- **Never read or print secret values**: do not call `secretsmanager get-secret-value`, do not cat
  `scripts/demo_credentials.local.json`, `frontend/.env.local`, `terraform.tfvars` or any token.
- Do not commit, push or open PRs. Do not edit source files.
- Write your findings only to `infra/instances/REVIEW-codex.md`.

## Report format (`infra/instances/REVIEW-codex.md`)

1. Verdict per desired result (1 to 6): WILL WORK / AT RISK / BROKEN, with evidence (file:line, command output).
2. Bugs and risks, most severe first, each with a concrete fix.
3. Anything that will make the video or Attribute data misleading or wrong.
4. What you could not verify and why.
