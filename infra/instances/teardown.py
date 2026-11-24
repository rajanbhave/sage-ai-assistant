"""Remove everything the Instances demo created, in dependency order, waiting at each step.

    uv run python -m infra.instances.teardown            # show what would be deleted
    uv run python -m infra.instances.teardown --confirm  # delete

Order: traffic -> runtimes -> capacity providers (and their managed EC2) -> artifact bucket -> stack
(VPC, NAT, EIP, roles, installer) -> log groups -> sensor-token secret. The shared Sage stack (Cognito pools,
pre-token Lambdas, Gateways, MCP runtimes, Sage API, the microVM lanes) is not touched.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

HERE = Path(__file__).parent
SECRET = "sage-reinvent/attribute-sensor-token"
TAG = "bedrock-agentcore:capacity-provider-id"


def wait_gone(get, label: str, minutes: int = 30) -> None:
    for _ in range(minutes * 6):
        try:
            status = get().get("status")
        except ClientError as e:
            if e.response["Error"]["Code"] in ("ResourceNotFoundException", "NotFoundException"):
                print(f"  {label}: gone")
                return
            raise
        print(f"  {label}: {status}")
        time.sleep(10)
    raise TimeoutError(f"{label} still present after {minutes} min")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--stack", default="sage-inst")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()

    out = json.loads((HERE / "instances_output.json").read_text())
    ctl = boto3.client("bedrock-agentcore-control", region_name=args.region)
    ec2 = boto3.client("ec2", region_name=args.region)
    cfn = boto3.client("cloudformation", region_name=args.region)
    logs = boto3.client("logs", region_name=args.region)
    s3 = boto3.resource("s3", region_name=args.region)
    sm = boto3.client("secretsmanager", region_name=args.region)

    outputs = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName=args.stack)["Stacks"][0]["Outputs"]}
    log_groups = [f"/aws/lambda/{outputs['SensorInstallerName']}"] + [
        g["logGroupName"]
        for r in out.values()
        for g in logs.describe_log_groups(logGroupNamePrefix=f"/aws/bedrock-agentcore/runtimes/{r['runtimeId']}")["logGroups"]
    ]
    plan = {
        "runtimes": [r["runtimeId"] for r in out.values()],
        "capacityProviders": [r["capacityProviderId"] for r in out.values()],
        "artifactBucket": outputs.get("ArtifactBucketName"),
        "stack": args.stack,
        "logGroups": log_groups,
        "secret": SECRET,
    }
    print(json.dumps(plan, indent=2))
    if not args.confirm:
        print("Dry run. Re-run with --confirm to delete.")
        return

    subprocess.run(["pkill", "-f", "infra.instances.traffic"], check=False)

    for rid in plan["runtimes"]:
        ctl.delete_agent_runtime(agentRuntimeId=rid)
    for rid in plan["runtimes"]:
        wait_gone(lambda: ctl.get_agent_runtime(agentRuntimeId=rid), f"runtime {rid}")

    for cp in plan["capacityProviders"]:
        ctl.delete_capacity_provider(capacityProviderId=cp)
    for cp in plan["capacityProviders"]:
        wait_gone(lambda: ctl.get_capacity_provider(capacityProviderId=cp), f"capacity provider {cp}")
    # Managed instances and their network interfaces must be gone before the VPC can be deleted.
    for _ in range(90):
        live = [
            i["InstanceId"]
            for page in ec2.get_paginator("describe_instances").paginate(
                IncludeManagedResources=True,
                Filters=[{"Name": "tag:" + TAG, "Values": plan["capacityProviders"]},
                         {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "shutting-down"]}],
            )
            for r in page["Reservations"]
            for i in r["Instances"]
        ]
        if not live:
            break
        print(f"  waiting for managed instances to terminate: {live}")
        time.sleep(10)

    if plan["artifactBucket"]:
        s3.Bucket(plan["artifactBucket"]).object_versions.delete()

    cfn.delete_stack(StackName=args.stack)
    cfn.get_waiter("stack_delete_complete").wait(StackName=args.stack, WaiterConfig={"Delay": 15, "MaxAttempts": 120})
    print(f"  stack {args.stack}: deleted")

    for g in log_groups:
        try:
            logs.delete_log_group(logGroupName=g)
            print(f"  log group {g}: deleted")
        except logs.exceptions.ResourceNotFoundException:
            pass

    try:
        sm.delete_secret(SecretId=SECRET, ForceDeleteWithoutRecovery=True)
        print(f"  secret {SECRET}: deleted")
    except sm.exceptions.ResourceNotFoundException:
        pass

    print(
        "Done. Still to do by hand:\n"
        " - point frontend/.env.local back at the microVM runtimes and remove the *_RUNTIME_SESSION_ID pins\n"
        " - decide whether to keep bluepine-user / oakhaven-user and their pre-token scope grants\n"
        " - rotate the Attribute sensor token (it was shared in a chat)\n"
        " - Attribute onboarding role: terraform destroy in ~/Documents/code_ws/doit/attribute-onboarding-434801484416"
    )


if __name__ == "__main__":
    main()
