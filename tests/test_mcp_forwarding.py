import io
import json

import pytest

import mcp_server.sage_api_client as module
from sage_identity import AuthenticationArtifact, CorrelationId
from mcp_server.sage_api_client import SageApiClient


def test_client_forwards_exact_bearer_and_correlation(monkeypatch):
    captured = {}
    def urlopen(request, timeout):
        captured["headers"] = {name.lower(): value for name, value in request.header_items()}
        captured["timeout"] = timeout
        return io.BytesIO(json.dumps({"products": []}).encode())
    monkeypatch.setattr(module, "urlopen", urlopen)
    result = SageApiClient("https://sage.example/v1").get_product_info(
        "motor", AuthenticationArtifact("original-bearer"), CorrelationId("b" * 32)
    )
    assert result == {"products": []}
    assert captured["headers"]["authorization"] == "Bearer original-bearer"
    assert captured["headers"]["x-sage-correlation-id"] == "b" * 32
    assert captured["timeout"] == 10.0


def test_client_requires_tls_except_on_loopback():
    with pytest.raises(ValueError, match="must use HTTPS"):
        SageApiClient("http://sage.internal/v1")

    assert SageApiClient("http://127.0.0.1:8081").base_url == "http://127.0.0.1:8081"
