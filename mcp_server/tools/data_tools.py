"""Data tools for the Sage MCP server.

These tools return tenant-scoped business data only through the configured
shared Sage API. Every tool derives request identity from the Runtime-validated
access token and trusted hosting-lane configuration, then forwards only the
exact received bearer and unchanged correlation ID.

Tool descriptions are crafted for AgentCore Gateway semantic routing
accuracy.
"""

from collections.abc import Callable
from dataclasses import dataclass

import json
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentHeaders
from fastmcp.exceptions import ToolError

from mcp_server.identity import (
    McpIdentityConfiguration,
    RequestIdentity,
    establish_request_identity,
    header_values,
)
from mcp_server.sage_api_client import SageApiClient, SageApiRequestError
from sage_identity import (
    AUTHORIZATION_HEADER,
    CORRELATION_HEADER,
    AuthenticationArtifact,
    CorrelationId,
    IdentityError,
    IdentityErrorCode,
    parse_bearer_authorization,
    serialize_identity_error,
    serialize_log_fields,
)

logger = logging.getLogger(__name__)


def _stable_failure(
    code: IdentityErrorCode, correlation_id: CorrelationId
) -> ToolError:
    """Log and expose only stable, non-secret failure fields."""
    error = IdentityError(code, correlation_id)
    logger.warning(
        "MCP data tool failed",
        extra={
            "identity_error": serialize_log_fields(
                {"code": error.code.value, "correlation_id": error.correlation_id}
            )
        },
    )
    return ToolError(
        json.dumps(serialize_identity_error(error), separators=(",", ":"))
    )


def _validated_result(payload: object, key: str) -> dict[str, object]:
    """Validate the small JSON shape returned by one Sage API operation."""
    if not isinstance(payload, dict) or key not in payload:
        raise TypeError("Sage API response does not match the tool result schema")
    value = payload[key]
    if key == "products" and not isinstance(value, list):
        raise TypeError("Sage API product result is invalid")
    if key == "claim" and value is not None and not isinstance(value, dict):
        raise TypeError("Sage API claim result is invalid")
    return payload


def _call_sage_api(
    call: Callable[[], dict[str, object]],
    result_key: str,
    correlation_id: CorrelationId,
) -> dict[str, object]:
    """Call the API and expose only its validated JSON result or safe failure."""
    try:
        return _validated_result(call(), result_key)
    except (SageApiRequestError, TypeError, ValueError, OSError):
        failure = _stable_failure(IdentityErrorCode.REQUEST_FAILED, correlation_id)
    raise failure


@dataclass(frozen=True, slots=True)
class _ValidatedRequest:
    identity: RequestIdentity
    bearer: AuthenticationArtifact
    correlation_id: CorrelationId


def _get_request(headers: dict) -> _ValidatedRequest:
    """Validate lane identity and retain only trusted outbound transport."""
    correlation_id = CorrelationId.new()
    try:
        correlation_values = header_values(headers, CORRELATION_HEADER)
        if len(correlation_values) != 1 or not isinstance(
            correlation_values[0], str
        ):
            raise ValueError("exactly one correlation header is required")
        correlation_id = CorrelationId(correlation_values[0])
        authorization_values = header_values(headers, AUTHORIZATION_HEADER)
        bearer = parse_bearer_authorization(authorization_values, correlation_id)
        identity = establish_request_identity(
            bearer,
            McpIdentityConfiguration.from_environment(),
            correlation_id,
        )
    except (IdentityError, ValueError):
        failure = _stable_failure(
            IdentityErrorCode.TENANT_IDENTITY_INVALID, correlation_id
        )
    else:
        return _ValidatedRequest(identity, bearer, correlation_id)
    raise failure


def _get_tenant(headers: dict) -> str:
    """Establish lane-bound request identity and return its signed tenant."""
    return _get_request(headers).identity.tenant_id


def register_data_tools(mcp: FastMCP) -> None:
    """Register all data tools onto the given FastMCP instance.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool(
        description=(
            "Get insurance product information for the current tenant. "
            "Use when the user asks about available products, product details, "
            "coverage options, pricing, premiums, or discounts for a specific "
            "product type (e.g. motor, home, life). Returns tenant-scoped product data."
        )
    )
    def get_product_info(
        product_type: str,
        headers: dict = CurrentHeaders(),
    ) -> dict:
        """Return tenant-scoped product details from the shared Sage API.

        Args:
            product_type: The product category to filter by (e.g. ``"motor"``).
            headers: Injected HTTP request headers (provided by FastMCP).

        Returns:
            The Sage API product response.

        Raises:
            ToolError: If identity validation or the Sage API request fails.
        """
        request = _get_request(headers)
        return _call_sage_api(
            lambda: SageApiClient.from_environment().get_product_info(
                product_type,
                request.bearer,
                request.correlation_id,
            ),
            "products",
            request.correlation_id,
        )

    @mcp.tool(
        description=(
            "Get details for a specific insurance claim by claim reference number. "
            "Use when the user asks about a claim status, claim amount, claim outcome, "
            "required documents for a claim, or any details about a specific claim "
            "identified by a reference like CLM-12345. Returns tenant-scoped claim data."
        )
    )
    def get_claim_details(
        claim_reference: str,
        headers: dict = CurrentHeaders(),
    ) -> dict:
        """Return tenant-scoped claim details from the shared Sage API.

        Args:
            claim_reference: The claim reference string (e.g. ``"CLM-12345"``).
            headers: Injected HTTP request headers (provided by FastMCP).

        Returns:
            The Sage API claim response.

        Raises:
            ToolError: If identity validation or the Sage API request fails.
        """
        request = _get_request(headers)
        return _call_sage_api(
            lambda: SageApiClient.from_environment().get_claim_details(
                claim_reference,
                request.bearer,
                request.correlation_id,
            ),
            "claim",
            request.correlation_id,
        )
