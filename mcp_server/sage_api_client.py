"""Same-bearer HTTP client for the shared Sage API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from sage_identity import (
    AuthenticationArtifact,
    CorrelationId,
    build_authorization_transport,
    build_correlation_headers,
)


class SageApiRequestError(Exception):
    """Non-secret failure raised when a Sage API request cannot complete."""

    def __init__(self) -> None:
        super().__init__("The Sage API request failed.")


@dataclass(frozen=True, slots=True)
class SageApiClient:
    """Call the configured shared Sage API with the received user bearer."""

    base_url: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme == "http"
                and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise ValueError(
                "SAGE_API_URL must use HTTPS, except for loopback local development"
            )
        if self.timeout_seconds <= 0:
            raise ValueError("Sage API timeout must be positive")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @classmethod
    def from_environment(cls) -> SageApiClient:
        """Load the shared Sage API endpoint from trusted deployment state."""
        return cls(os.environ.get("SAGE_API_URL", ""))

    def get_product_info(
        self,
        product_type: str,
        bearer: AuthenticationArtifact,
        correlation_id: CorrelationId,
    ) -> dict[str, object]:
        """Fetch product information without forwarding tenant authority."""
        return self._get(
            "/products",
            {"product_type": product_type},
            bearer,
            correlation_id,
        )

    def get_claim_details(
        self,
        claim_reference: str,
        bearer: AuthenticationArtifact,
        correlation_id: CorrelationId,
    ) -> dict[str, object]:
        """Fetch claim details without forwarding tenant authority."""
        return self._get(
            "/claims",
            {"claim_reference": claim_reference},
            bearer,
            correlation_id,
        )

    def _get(
        self,
        path: str,
        query: dict[str, str],
        bearer: AuthenticationArtifact,
        correlation_id: CorrelationId,
    ) -> dict[str, object]:
        headers = build_authorization_transport(bearer).as_headers()
        headers.update(build_correlation_headers(correlation_id))
        headers["Accept"] = "application/json"
        request = Request(
            f"{self.base_url}{path}?{urlencode(query)}",
            headers=headers,
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
            raise SageApiRequestError() from None

        if not isinstance(payload, dict) or any(
            not isinstance(key, str) for key in payload
        ):
            raise SageApiRequestError()
        return payload
