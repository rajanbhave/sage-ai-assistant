import importlib
import sys

import boto3

from sage_identity import AuthenticationArtifact, CorrelationId


class _EmptyRegistry:
    def list_registry_records(self, **_kwargs):
        return {"registryRecords": []}


def test_agent_forwards_exact_original_bearer(monkeypatch, request):
    monkeypatch.setenv("GATEWAY_URL", "https://gateway.example/mcp")
    monkeypatch.setenv("SKILL_REGISTRY_ID", "registry")
    monkeypatch.setattr(boto3, "client", lambda *_args, **_kwargs: _EmptyRegistry())
    sys.modules.pop("agent.agent", None)
    request.addfinalizer(lambda: sys.modules.pop("agent.agent", None))
    module = importlib.import_module("agent.agent")
    captured = {}

    class _Client:
        def __init__(self, transport):
            self.transport = transport

    def streamable(url, headers):
        captured.update(url=url, headers=headers)

    monkeypatch.setattr(module, "MCPClient", _Client)
    monkeypatch.setattr(module, "streamablehttp_client", streamable)
    bearer = "AbC.def-123_~+/="

    client = module._make_mcp_client(
        AuthenticationArtifact(bearer), CorrelationId("c" * 32)
    )
    client.transport()

    assert captured == {
        "url": "https://gateway.example/mcp",
        "headers": {
            "Authorization": f"Bearer {bearer}",
            "X-Sage-Correlation-Id": "c" * 32,
        },
    }
