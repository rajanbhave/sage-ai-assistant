"""Clone Sage's tenant agent runtimes onto AgentCore Runtime Instances.

One capacity provider per tenant lane, so the Attribute sensor installer can name each
EC2 workload after its lane. The new runtimes reuse the source runtime's code artifact,
role, JWT authorizer, header allowlist and environment; the existing microVM runtimes
are left untouched.

    uv run python -m infra.instances.deploy_instances --dry-run
    uv run python -m infra.instances.deploy_instances
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import boto3

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
DEFAULT_LANES = {
    # laneId: (source microVM runtime id, Attribute workload name, tenant label for requestMetadata)
    "Tenant_A": ("sage_agent_tenant_a-aYtwN59JV2", "sage-agent-bluepine", "bluepine"),
    "Tenant_B": ("sage_agent_tenant_b-JJJ3NmHHHE", "sage-agent-oakhaven", "oakhaven"),
}
INSTANCE_TYPES = ["c7g.large", "c7g.xlarge"]
IDLE_SECONDS = 900
MAX_LIFETIME_SECONDS = 8 * 3600
COPIED_FIELDS = (
    "agentRuntimeArtifact",
    "roleArn",
    "protocolConfiguration",
    "authorizerConfiguration",
    "requestHeaderConfiguration",
    "environmentVariables",
)


def capacity_provider_request(name: str, outputs: dict) -> dict:
    return {
        "name": name,
        "description": "Sage on AgentCore Instances (re:Invent 2026 demo)",
        "permissionsConfiguration": {"capacityProviderOperatorRoleArn": outputs["OperatorRoleArn"]},
        "computeConfiguration": {
            "ec2Configuration": {
                "launchTemplateSource": {
                    "launchParameters": {
                        "operatingSystem": "LINUX_ARM64",  # Sage's zip is built for linux/arm64
                        "instanceRequirements": {"allowedInstanceTypes": INSTANCE_TYPES},
                        "instanceProfileArn": outputs["InstanceProfileArn"],
                    }
                },
                "vpcConfiguration": {
                    "subnets": outputs["SubnetIds"].split(","),
                    "securityGroups": [outputs["SecurityGroupId"]],
                },
                "lifecycleConfiguration": {
                    "idleInstanceTimeout": IDLE_SECONDS,
                    "maxLifetime": MAX_LIFETIME_SECONDS,
                },
            }
        },
    }


def runtime_request(source: dict, name: str, capacity_provider_arn: str, tenant_label: str = "") -> dict:
    """Copy what defines the agent's behaviour; drop network config, which Instances reject."""
    request = {k: source[k] for k in COPIED_FIELDS if source.get(k)}
    if tenant_label:
        request["environmentVariables"] = {**request.get("environmentVariables", {}), "SAGE_TENANT_LABEL": tenant_label}
    request.update(
        agentRuntimeName=name,
        description=f"{source['agentRuntimeName']} on AgentCore Instances",
        capacityProviderConfiguration={"capacityProviderArn": capacity_provider_arn},
        lifecycleConfiguration={
            "idleRuntimeSessionTimeout": IDLE_SECONDS,
            "maxLifetime": MAX_LIFETIME_SECONDS,  # must not exceed the capacity provider's
        },
    )
    return request


def invocation_url(region: str, runtime_arn: str) -> str:
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
        f"{quote(runtime_arn, safe='')}/invocations?qualifier=DEFAULT"
    )


def build_artifact(source_artifact: dict, region: str, bucket: str) -> dict:
    """Rebuild the zip with the starter toolkit's packager and upload it next to the original.

    The toolkit's bucket expires every object after 7 days, so the zip goes to the stack's own bucket
    (no lifecycle rule) under a content-addressed key that is never overwritten.
    Only git-tracked files are packaged, which keeps local config and credentials out of the zip.
    """
    from bedrock_agentcore_starter_toolkit.utils.runtime.entrypoint import detect_dependencies
    from bedrock_agentcore_starter_toolkit.utils.runtime.package import CodeZipPackager

    code = source_artifact["codeConfiguration"]
    work = Path(tempfile.mkdtemp(prefix="sage-inst-"))
    src = work / "src"
    for rel in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines():
        if (ROOT / rel).is_file():
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, src / rel)
    deps = detect_dependencies(src)
    zip_path, _ = CodeZipPackager().create_deployment_package(
        source_dir=src,
        agent_name="sage_agent_inst",
        cache_dir=work / "cache",
        runtime_version=code["runtime"],
        requirements_file=Path(deps.resolved_path) if deps.found else None,
    )
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()[:16]
    key = f"sage_agent_inst/deployment-{digest}.zip"
    boto3.client("s3", region_name=region).upload_file(str(zip_path), bucket, key)
    shutil.rmtree(work, ignore_errors=True)
    print(f"Uploaded s3://{bucket}/{key}")
    return {"codeConfiguration": {**code, "code": {"s3": {"bucket": bucket, "prefix": key}}}}


def deploy_installer(lam, function_name: str) -> None:
    """Ship sensor_installer.py with a current boto3 (Lambda's bundled one may lack IncludeManagedResources)."""
    work = Path(tempfile.mkdtemp(prefix="sage-installer-"))
    subprocess.run(
        ["uv", "pip", "install", "--quiet", "--target", str(work), "--python-platform", "x86_64-manylinux2014",
         "--python-version", "3.13", "boto3"],
        check=True,
    )
    shutil.copy2(HERE / "sensor_installer.py", work / "sensor_installer.py")
    archive = shutil.make_archive(str(work.parent / work.name), "zip", work)
    lam.update_function_code(FunctionName=function_name, ZipFile=Path(archive).read_bytes())
    lam.get_waiter("function_updated_v2").wait(FunctionName=function_name)
    shutil.rmtree(work, ignore_errors=True)
    Path(archive).unlink(missing_ok=True)
    print(f"Deployed {function_name}")


def wait_ready(get, label: str, minutes: int = 20) -> dict:
    for _ in range(minutes * 6):
        item = get()
        status = item.get("status")
        if status == "READY":
            return item
        if status and "FAIL" in status:
            raise RuntimeError(f"{label} {status}: {item.get('failureReason', item)}")
        print(f"  {label}: {status}")
        time.sleep(10)
    raise TimeoutError(f"{label} not READY after {minutes} min")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--stack", default="sage-inst")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rebuild", action="store_true", help="repackage the code and update existing runtimes")
    p.add_argument("--output", type=Path, default=HERE / "instances_output.json")
    args = p.parse_args()

    cfn = boto3.client("cloudformation", region_name=args.region)
    ctl = boto3.client("bedrock-agentcore-control", region_name=args.region)
    lam = boto3.client("lambda", region_name=args.region)

    stack = cfn.describe_stacks(StackName=args.stack)["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}

    # Re-runs reuse what already exists instead of creating duplicates.
    existing_cps = {c["name"]: c["capacityProviderId"] for c in ctl.list_capacity_providers().get("capacityProviders", [])}
    existing_rts = {r["agentRuntimeName"]: r["agentRuntimeId"] for r in ctl.list_agent_runtimes().get("agentRuntimes", [])}
    artifact = None

    result, workload_map = {}, {}
    for lane, (source_id, workload, tenant_label) in DEFAULT_LANES.items():
        suffix = lane[-1].lower()
        source = ctl.get_agent_runtime(agentRuntimeId=source_id)
        cp_req = capacity_provider_request(f"sage_inst_cp_{suffix}", outputs)
        if args.dry_run:
            preview = runtime_request(source, f"sage_agent_inst_{suffix}", "<capacity-provider-arn>", tenant_label)
            preview["environmentVariables"] = sorted(preview.get("environmentVariables", {}))  # names only
            print(json.dumps({"lane": lane, "capacityProvider": cp_req, "runtime": preview}, indent=2, default=str))
            continue

        cp_id = existing_cps.get(cp_req["name"]) or ctl.create_capacity_provider(**cp_req)["capacityProviderId"]
        cp = wait_ready(lambda: ctl.get_capacity_provider(capacityProviderId=cp_id), f"capacity provider {lane}")

        rt_name = f"sage_agent_inst_{suffix}"
        rt_id = existing_rts.get(rt_name)
        if rt_id and args.rebuild:
            artifact = artifact or build_artifact(source["agentRuntimeArtifact"], args.region, outputs["ArtifactBucketName"])
            update = runtime_request({**source, "agentRuntimeArtifact": artifact}, rt_name, cp["capacityProviderArn"], tenant_label)
            del update["agentRuntimeName"]
            ctl.update_agent_runtime(agentRuntimeId=rt_id, **update)
        if not rt_id:
            artifact = artifact or build_artifact(source["agentRuntimeArtifact"], args.region, outputs["ArtifactBucketName"])
            rt_id = ctl.create_agent_runtime(
                **runtime_request({**source, "agentRuntimeArtifact": artifact}, rt_name, cp["capacityProviderArn"], tenant_label)
            )["agentRuntimeId"]
        rt = wait_ready(lambda: ctl.get_agent_runtime(agentRuntimeId=rt_id), f"runtime {lane}")

        workload_map[cp_id] = workload
        result[lane] = {
            "workload": workload,
            "capacityProviderId": cp_id,
            "runtimeId": rt_id,
            "runtimeArn": rt["agentRuntimeArn"],
            "invocationUrl": invocation_url(args.region, rt["agentRuntimeArn"]),
        }

    if args.dry_run:
        return

    # Merge so a re-run for one lane does not drop the other lane's mapping.
    fn = outputs["SensorInstallerName"]
    deploy_installer(lam, fn)
    env = lam.get_function_configuration(FunctionName=fn)["Environment"]["Variables"]
    env["WORKLOAD_MAP"] = json.dumps({**json.loads(env.get("WORKLOAD_MAP", "{}")), **workload_map})
    lam.update_function_configuration(FunctionName=fn, Environment={"Variables": env})

    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {args.output}")
    for lane, r in result.items():
        print(f"VITE_TENANT_{lane[-1]}_AGENT_RUNTIME_ENDPOINT={r['invocationUrl']}")


if __name__ == "__main__":
    main()
