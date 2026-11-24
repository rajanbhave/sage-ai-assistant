from infra.instances.deploy_instances import capacity_provider_request, invocation_url, runtime_request

OUTPUTS = {
    "OperatorRoleArn": "arn:aws:iam::1:role/op",
    "InstanceProfileArn": "arn:aws:iam::1:instance-profile/ip",
    "SubnetIds": "subnet-a,subnet-b",
    "SecurityGroupId": "sg-1",
}
SOURCE = {
    "agentRuntimeName": "sage_agent_tenant_a",
    "agentRuntimeArtifact": {"codeConfiguration": {"runtime": "PYTHON_3_13"}},
    "roleArn": "arn:aws:iam::1:role/rt",
    "authorizerConfiguration": {"customJWTAuthorizer": {"discoveryUrl": "https://x"}},
    "requestHeaderConfiguration": {"requestHeaderAllowlist": ["Authorization"]},
    "environmentVariables": {"GATEWAY_URL": "https://gw"},
    "networkConfiguration": {"networkMode": "PUBLIC"},
    "status": "READY",
}


def test_runtime_request_keeps_auth_and_drops_network():
    req = runtime_request(SOURCE, "sage_agent_inst_a", "arn:cp")
    assert req["authorizerConfiguration"] == SOURCE["authorizerConfiguration"]
    assert req["requestHeaderConfiguration"] == SOURCE["requestHeaderConfiguration"]
    assert req["environmentVariables"] == SOURCE["environmentVariables"]
    assert req["capacityProviderConfiguration"] == {"capacityProviderArn": "arn:cp"}
    assert "networkConfiguration" not in req and "status" not in req
    cp = capacity_provider_request("cp", OUTPUTS)["computeConfiguration"]["ec2Configuration"]
    assert req["lifecycleConfiguration"]["maxLifetime"] <= cp["lifecycleConfiguration"]["maxLifetime"]


def test_capacity_provider_is_arm_in_private_subnets():
    ec2 = capacity_provider_request("cp", OUTPUTS)["computeConfiguration"]["ec2Configuration"]
    assert ec2["launchTemplateSource"]["launchParameters"]["operatingSystem"] == "LINUX_ARM64"
    assert ec2["vpcConfiguration"] == {"subnets": ["subnet-a", "subnet-b"], "securityGroups": ["sg-1"]}


def test_invocation_url_encodes_arn():
    url = invocation_url("us-east-1", "arn:aws:bedrock-agentcore:us-east-1:1:runtime/x-1")
    assert url == (
        "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/"
        "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A1%3Aruntime%2Fx-1/invocations?qualifier=DEFAULT"
    )


def test_runtime_request_adds_tenant_label_without_dropping_env():
    req = runtime_request(SOURCE, "n", "arn:cp", "bluepine")
    assert req["environmentVariables"] == {"GATEWAY_URL": "https://gw", "SAGE_TENANT_LABEL": "bluepine"}
    assert SOURCE["environmentVariables"] == {"GATEWAY_URL": "https://gw"}  # source not mutated


def test_model_request_carries_tenant_metadata(monkeypatch, request):
    import importlib
    import sys

    import boto3

    class _EmptyRegistry:
        def list_registry_records(self, **_kwargs):
            return {"registryRecords": []}

    monkeypatch.setenv("GATEWAY_URL", "https://gateway.example/mcp")
    monkeypatch.setenv("SKILL_REGISTRY_ID", "registry")
    monkeypatch.setattr(boto3, "client", lambda *_a, **_k: _EmptyRegistry())
    sys.modules.pop("agent.agent", None)
    request.addfinalizer(lambda: sys.modules.pop("agent.agent", None))
    a = importlib.import_module("agent.agent")
    monkeypatch.setattr(a, "TENANT_LABEL", "oakhaven")
    req = a.model.format_request([{"role": "user", "content": [{"text": "hi"}]}])
    assert req["requestMetadata"] == {"x-tenant-id": "oakhaven"}


def test_traffic_outcome_detects_stream_errors():
    from infra.instances.traffic import outcome

    ok = 'data: {"event": {"contentBlockDelta": {"delta": {"text": "Hi"}}}}\n'
    err = 'data: {"code": "session_expired", "message": "x", "correlation_id": "c"}\n'
    assert outcome(200, ok) == "ok"
    assert outcome(200, err) == "stream_error_session_expired"
    assert outcome(200, "data: {}\n") == "no_answer"
    assert outcome(424, "boom") == "http_424"
