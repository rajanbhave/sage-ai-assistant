"""Production tenant-lane, issuer, and deployment-evidence records."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum

TENANT_A = "Tenant_A"
TENANT_B = "Tenant_B"
_REQUIRED_TENANTS = frozenset({TENANT_A, TENANT_B})


class ManagedDoor(str, Enum):
    """Managed authorization boundaries deployed once per tenant lane."""

    AGENT_RUNTIME = "agent_runtime"
    GATEWAY = "gateway"
    MCP_RUNTIME = "mcp_runtime"


@dataclass(frozen=True, slots=True)
class TenantLaneConfiguration:
    """Immutable deployment binding for one fixed tenant lane."""

    lane_id: str
    tenant_id: str
    user_pool_id: str
    issuer: str
    discovery_url: str
    frontend_client_ids: frozenset[str]
    agent_runtime_endpoint: str
    agent_runtime_id: str
    gateway_id: str
    gateway_target_url: str
    mcp_runtime_id: str
    expected_tenant_claim: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "frontend_client_ids", frozenset(self.frontend_client_ids))
        if (
            self.lane_id not in _REQUIRED_TENANTS
            or self.tenant_id != self.lane_id
            or self.expected_tenant_claim != self.lane_id
        ):
            raise ValueError("lane, tenant, and expected claim must be Tenant_A or Tenant_B and match")


@dataclass(frozen=True, slots=True)
class ApiIssuerConfiguration:
    """Immutable Sage API validation configuration for one allowed issuer."""

    issuer: str
    discovery_url: str
    expected_tenant_id: str
    trusted_client_ids: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "trusted_client_ids", frozenset(self.trusted_client_ids))
        if self.expected_tenant_id not in _REQUIRED_TENANTS:
            raise ValueError("API tenant must be Tenant_A or Tenant_B")


@dataclass(frozen=True, slots=True)
class AllowedTenantIssuerMap(Mapping[str, ApiIssuerConfiguration]):
    """Immutable issuer map for the two lane issuers."""

    entries: tuple[ApiIssuerConfiguration, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))

    def __getitem__(self, issuer: str) -> ApiIssuerConfiguration:
        for entry in self.entries:
            if entry.issuer == issuer:
                return entry
        raise KeyError(issuer)

    def __iter__(self) -> Iterator[str]:
        return (entry.issuer for entry in self.entries)

    def __len__(self) -> int:
        return len(self.entries)


@dataclass(frozen=True, slots=True)
class TargetCapabilityEvidence:
    """Immutable documentation and deployed-target evidence for one lane."""

    lane_id: str
    target_type: str
    documentation_url: str
    retrieval_date: date
    protocol_type: str
    credential_provider_type: str
    endpoint: str
    jwt_passthrough_documentation_url: str = ""
    deployed_configuration_evidence: str = ""
    expected_endpoint: str = ""
    endpoint_matches: bool = False


@dataclass(frozen=True, slots=True)
class SourceSignalProofRecord:
    """Immutable evidence for a lane's conditional Gateway source signal."""

    lane_id: str
    candidate_mechanism: str
    documentation_evidence: str
    deployed_configuration_evidence: str
    behavioral_verified: bool
    source_signal_available: bool
    exact_topology_documented: bool = False
    same_lane_configuration_verified: bool = False
    missing_source_rejected_before_protected_behavior: bool = False
    wrong_lane_source_rejected_before_protected_behavior: bool = False
