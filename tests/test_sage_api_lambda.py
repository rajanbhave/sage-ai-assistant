import json

import sage_api.lambda_handler as lambda_module


def function_url_event(**headers: str) -> dict:
    return {
        "rawPath": "/claims",
        "rawQueryString": "claim_reference=CLM-12345",
        "requestContext": {"http": {"method": "GET"}},
        "headers": headers,
    }


def test_adapter_maps_transport_and_returns_the_wsgi_status(monkeypatch):
    captured: dict = {}

    def fake_application(environ, start_response):
        captured.update(environ)
        start_response("403 Forbidden", [("Content-Type", "application/json")])
        return [json.dumps({"code": "not_authorized"}).encode()]

    monkeypatch.setattr(lambda_module, "application", fake_application)
    monkeypatch.setenv("SAGE_API_SOURCE_PATH", "approved-source")

    response = lambda_module.lambda_handler(
        function_url_event(**{
            "authorization": "Bearer token",
            "x-sage-correlation-id": "a" * 32,
        }),
        None,
    )

    assert response["statusCode"] == 403
    assert json.loads(response["body"]) == {"code": "not_authorized"}
    assert captured["REQUEST_METHOD"] == "GET"
    assert captured["PATH_INFO"] == "/claims"
    assert captured["QUERY_STRING"] == "claim_reference=CLM-12345"
    assert captured["HTTP_AUTHORIZATION"] == "Bearer token"
    assert captured["HTTP_X_SAGE_CORRELATION_ID"] == "a" * 32
    # The source path is deployment-asserted, never read from the caller.
    assert captured["sage.source_path"] == "approved-source"


def test_adapter_never_takes_the_source_path_from_the_caller(monkeypatch):
    captured: dict = {}

    def fake_application(environ, start_response):
        captured.update(environ)
        start_response("200 OK", [])
        return [b"{}"]

    monkeypatch.setattr(lambda_module, "application", fake_application)
    monkeypatch.setenv("SAGE_API_SOURCE_PATH", "approved-source")

    lambda_module.lambda_handler(
        function_url_event(**{"sage-source-path": "spoofed"}),
        None,
    )

    assert captured["sage.source_path"] == "approved-source"
