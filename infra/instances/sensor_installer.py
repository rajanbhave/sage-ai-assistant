"""Install the DoiT Attribute sensor on AgentCore Runtime Instances (runs every minute).

AgentCore's EC2 managed instances emit no state-change events to the account's event bus and are
hidden from DescribeInstances unless IncludeManagedResources is set, so this polls instead. It is
packaged with a current boto3 by deploy_instances.py, because Lambda's bundled boto3 may predate
that parameter.
"""

import json
import os

import boto3

ec2, ssm = boto3.client("ec2"), boto3.client("ssm")
TAG = "bedrock-agentcore:capacity-provider-id"
COMMENT = "Attribute sensor"


def _commands(workload: str) -> list[str]:
    region, secret, mem = os.environ["AWS_REGION"], os.environ["SECRET_NAME"], os.environ["MEMORY_LIMIT"]
    # The token is fetched on the instance with its own role, so it never appears in SSM command history.
    return [
        "set -euo pipefail",
        "systemctl is-active --quiet zprobe && { echo 'sensor already running'; exit 0; }",
        "echo 'prefer-family = IPv4' >> /etc/wgetrc",
        # DNS returns IPv6 first but the subnet has no IPv6 route, so calls hang until signatures expire.
        "grep -q '^precedence ::ffff:0:0/96' /etc/gai.conf 2>/dev/null || echo 'precedence ::ffff:0:0/96 100' >> /etc/gai.conf",
        "export AWS_USE_DUALSTACK_ENDPOINT=false",
        f"TOKEN=$(aws secretsmanager get-secret-value --region {region} --secret-id {secret} "
        "--cli-connect-timeout 10 --query SecretString --output text | python3 -c 'import json,sys;print(json.load(sys.stdin)[\"token\"])')",
        "cd /tmp && wget -q https://storage.googleapis.com/attrb-artifacts/standalone-install.sh && chmod +x standalone-install.sh",
        f'./standalone-install.sh {workload} {mem} "$TOKEN"',
        "systemctl start zprobe && sleep 5 && systemctl is-active zprobe && journalctl -u zprobe -n 5 --no-pager",
    ]


def _already_tried(iid: str) -> bool:
    for cmd in ssm.list_commands(InstanceId=iid)["Commands"]:
        if cmd.get("Comment", "").startswith(COMMENT) and cmd["Status"] in ("Pending", "InProgress", "Success"):
            return True
    return False


def _online(iid: str) -> bool:
    info = ssm.describe_instance_information(Filters=[{"Key": "InstanceIds", "Values": [iid]}])["InstanceInformationList"]
    return bool(info) and info[0].get("PingStatus") == "Online"


def handler(_event, _ctx):
    workloads = json.loads(os.environ["WORKLOAD_MAP"])
    pages = ec2.get_paginator("describe_instances").paginate(
        IncludeManagedResources=True,
        Filters=[{"Name": "tag-key", "Values": [TAG]}, {"Name": "instance-state-name", "Values": ["running"]}],
    )
    started = []
    for page in pages:
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                iid = inst["InstanceId"]
                cp = next(t["Value"] for t in inst.get("Tags", []) if t["Key"] == TAG)
                workload = workloads.get(cp)
                # Not ours, SSM not up yet (retried next minute), or already handled.
                if not workload or not _online(iid) or _already_tried(iid):
                    continue
                cmd = ssm.send_command(
                    InstanceIds=[iid],
                    DocumentName="AWS-RunShellScript",
                    Parameters={"commands": _commands(workload), "executionTimeout": ["600"]},
                    Comment=f"{COMMENT} ({workload})",
                )["Command"]["CommandId"]
                started.append({"instance": iid, "workload": workload, "command": cmd})
    print(json.dumps({"started": started}))
    return {"started": started}
