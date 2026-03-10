"""Data tools for the Sage MCP server.

These tools return tenant-scoped business data from the in-memory mock
store. Every tool reads the tenant ID from the
``X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id`` request header —
never from user input.

Tool descriptions are crafted for AgentCore Gateway semantic routing
accuracy.
"""

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentHeaders
from fastmcp.exceptions import ToolError

from mcp_server.mock_data import MOCK_DATA

TENANT_HEADER = "x-amzn-bedrock-agentcore-runtime-custom-tenant-id"


def _get_tenant(headers: dict) -> str:
    """Extract and validate the tenant ID from request headers.

    Args:
        headers: HTTP request headers dict (lowercased keys from FastMCP).

    Returns:
        Validated tenant ID string.

    Raises:
        ToolError: If the header is missing or the tenant is unknown.
    """
    tenant_id = headers.get(TENANT_HEADER, "").strip().lower()
    if not tenant_id:
        raise ToolError(
            f"Missing required header '{TENANT_HEADER}'. "
            "error_type: invalid_tenant"
        )
    if tenant_id not in MOCK_DATA:
        raise ToolError(
            f"Unknown tenant '{tenant_id}'. "
            "error_type: invalid_tenant"
        )
    return tenant_id


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
        """Return product details for the given type, scoped to the current tenant.

        Reads the tenant ID from the
        ``X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id`` header and
        returns all products of the requested type for that tenant.

        Args:
            product_type: The product category to filter by (e.g. ``"motor"``).
            headers: Injected HTTP request headers (provided by FastMCP).

        Returns:
            Dict with ``tenant``, ``product_type``, and ``products`` list.

        Raises:
            ToolError: If the tenant header is missing, unknown, or no
                products match the requested type.
        """
        tenant_id = _get_tenant(headers)
        products = [
            p for p in MOCK_DATA[tenant_id]["products"]
            if p["type"].lower() == product_type.lower()
        ]
        if not products:
            raise ToolError(
                f"No '{product_type}' products found for tenant '{tenant_id}'. "
                "error_type: not_found"
            )
        return {"tenant": tenant_id, "product_type": product_type, "products": products}

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
        """Return details for a specific claim, scoped to the current tenant.

        Reads the tenant ID from the
        ``X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id`` header and
        looks up the claim within that tenant's data only.

        Args:
            claim_reference: The claim reference string (e.g. ``"CLM-12345"``).
            headers: Injected HTTP request headers (provided by FastMCP).

        Returns:
            Dict with the full claim record.

        Raises:
            ToolError: If the tenant header is missing/unknown, or the claim
                reference is not found for this tenant.
        """
        tenant_id = _get_tenant(headers)
        claims = MOCK_DATA[tenant_id]["claims"]
        for claim in claims:
            if claim["claim_reference"].upper() == claim_reference.upper():
                return {"tenant": tenant_id, "claim": claim}
        raise ToolError(
            f"Claim '{claim_reference}' not found for tenant '{tenant_id}'. "
            "error_type: not_found"
        )
