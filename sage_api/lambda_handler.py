"""Lambda Function URL adapter for the shared Sage API WSGI boundary.

The Sage API is a WSGI application. This module adapts a Lambda Function URL
payload (format 2.0) into a WSGI environ and returns the Function URL response
shape. All validation, authorization, and tenant isolation stay in
``sage_api.http``; this module only translates transport.

Source-path honesty
-------------------
``SageApiApplication`` requires ``sage.source_path`` to be an approved value and
refuses to treat caller-controlled data as source authority. A public Function
URL has no trusted private ingress, so there is no caller property this adapter
could honestly use. It therefore injects a constant supplied at deployment time
through ``SAGE_API_SOURCE_PATH``, which means the source control is effectively
asserted by deployment rather than verified per request. Deployments using this
adapter must record the source-signal control as unavailable instead of claiming
a verified same-lane restriction. Independent JWT validation, subject and tenant
authorization, and tenant data isolation are unaffected.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from io import BytesIO
from typing import Any

from .http import application

_DEFAULT_SOURCE_PATH = "sage-mcp-runtime"


def _environ(event: Mapping[str, Any]) -> dict[str, Any]:
    request = event.get("requestContext")
    http = request.get("http") if isinstance(request, Mapping) else None
    method = http.get("method") if isinstance(http, Mapping) else None
    raw_path = event.get("rawPath")
    raw_query = event.get("rawQueryString")

    environ: dict[str, Any] = {
        "REQUEST_METHOD": method if isinstance(method, str) else "",
        "PATH_INFO": raw_path if isinstance(raw_path, str) else "/",
        "QUERY_STRING": raw_query if isinstance(raw_query, str) else "",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "https",
        "wsgi.input": BytesIO(b""),
        "wsgi.errors": None,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        # Deployment-asserted; see the module docstring.
        "sage.source_path": os.environ.get(
            "SAGE_API_SOURCE_PATH", _DEFAULT_SOURCE_PATH
        ),
    }

    headers = event.get("headers")
    if isinstance(headers, Mapping):
        for name, value in headers.items():
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            key = f"HTTP_{name.upper().replace('-', '_')}"
            # A repeated header arrives comma-joined; the strict Authorization
            # parser downstream rejects such a value rather than splitting it.
            environ[key] = value

    return environ


def lambda_handler(
    event: Mapping[str, Any], _context: object
) -> dict[str, Any]:
    """Translate one Function URL request into the Sage API WSGI call."""
    captured: dict[str, Any] = {}

    def start_response(
        status: str, headers: list[tuple[str, str]], exc_info: object = None
    ) -> None:
        del exc_info
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(application(_environ(event), start_response))
    status = str(captured.get("status", "500 Internal Server Error"))
    headers = captured.get("headers") or []

    return {
        "statusCode": int(status.split(" ", 1)[0]),
        "headers": {name: value for name, value in headers},
        "body": body.decode("utf-8"),
        "isBase64Encoded": False,
    }
