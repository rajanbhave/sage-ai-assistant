"""Topology identifiers for tests, read from the environment instead of literals.

Resolution order for every key:

1. ``os.environ``
2. the file named by ``SAGE_TEST_ENV_FILE``
3. the repository ``.env`` (gitignored; put real deployment values there)
4. ``tests/topology.env`` (committed placeholders, so CI and a fresh clone run)

Pointing a key at a real runtime, gateway, or pool therefore needs no test edit,
and no test carries a deployment identifier of its own.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_FILE = Path(__file__).resolve().parent / "topology.env"


def _parse(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


@cache
def _file_values() -> dict[str, str]:
    """Merge the candidate files, lowest precedence first."""
    merged = _parse(DEFAULTS_FILE)
    merged.update(_parse(PROJECT_ROOT / ".env"))
    override = os.environ.get("SAGE_TEST_ENV_FILE", "").strip()
    if override:
        merged.update(_parse(Path(override)))
    return merged


def topology(key: str) -> str:
    """Return one topology value, or raise if no source defines it."""
    value = os.environ.get(key) or _file_values().get(key, "")
    if not value.strip():
        raise KeyError(
            f"{key} is not set in the environment, .env, or tests/topology.env"
        )
    return value.strip()


def lane_topology(lane_id: str) -> dict[str, str]:
    """Return the manifest-shaped record for one lane."""
    prefix = f"SAGE_TEST_{lane_id.upper()}"
    return {
        "laneId": lane_id,
        "userPoolId": topology(f"{prefix}_USER_POOL_ID"),
        "frontendClientIds": [topology(f"{prefix}_CLIENT_ID")],
        "mcpRuntimeArn": topology(f"{prefix}_MCP_RUNTIME_ARN"),
        "mcpRuntimeQualifier": topology("SAGE_TEST_TENANT_A_MCP_RUNTIME_QUALIFIER"),
        "gatewayId": topology(f"{prefix}_GATEWAY_ID"),
        "gatewayTargetUrl": topology("SAGE_TEST_TENANT_A_GATEWAY_TARGET_URL"),
        "agentRuntimeEndpoint": topology(
            "SAGE_TEST_TENANT_A_AGENT_RUNTIME_ENDPOINT"
        ),
    }
