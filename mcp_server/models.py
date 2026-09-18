"""Shared data models for the Sage MCP server.

Defines the canonical types used by data tools. These are plain
dataclasses — no ORM, no serialization framework.
"""

from dataclasses import dataclass, field
from enum import Enum


class TenantId(str, Enum):
    """Valid internal tenant identifiers."""

    TENANT_A = "Tenant_A"
    TENANT_B = "Tenant_B"


@dataclass
class ProductInfo:
    """Tenant-scoped insurance product details."""

    product_id: str
    name: str
    type: str
    base_premium: float
    currency: str
    coverage: dict
    discounts: list[dict] = field(default_factory=list)


@dataclass
class ClaimDetails:
    """Tenant-scoped insurance claim details."""

    claim_reference: str
    policy_id: str
    status: str
    amount: float
    currency: str
    incident_date: str
    description: str
    documents_required: list[str] = field(default_factory=list)
    notes: str = ""
