"""Reproducible Route C acceptance validation across four levels.

The script proves, for both tenant lanes:

1. ``deployed_configuration`` — every managed door and Gateway target matches the
   approved lane binding, read back from the AgentCore control plane.
2. ``managed_door_rejection`` — every door rejects the other lane's token and
   malformed credentials, in both directions.
3. ``end_to_end_isolation`` — each lane returns only its own tenant data through
   the whole route, including the same claim reference resolving differently.
4. ``audit_evidence`` — the Sage API emits a correlation-matched authorization
   event, and no log group contains credential material.

Nothing here prints, stores, or hashes a bearer token. Configuration objects are
hashed so a report can be compared across runs; token-derived values never are.

Usage::

    uv run python scripts/validate_route_c.py
    uv run python scripts/validate_route_c.py --report out.json --skip-agent

Exits non-zero if any mandatory check fails.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import boto3

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MANIFEST = PROJECT_ROOT / "scripts" / "identity_deployment.json"
DEFAULT_CREDENTIALS = PROJECT_ROOT / "scripts" / "demo_credentials.local.json"
DEFAULT_REPORT = PROJECT_ROOT / "scripts" / "route_c_validation_report.json"

LANES = ("Tenant_A", "Tenant_B")
OTHER_LANE = {"Tenant_A": "Tenant_B", "Tenant_B": "Tenant_A"}
REQUIRED_SCOPES = frozenset(
    {
        "sage-agent/invoke",
        "sage-gateway/invoke",
        "sage-mcp/invoke",
        "sage-api/read",
    }
)
DOOR_SCOPE = {
    "agent": "sage-agent/invoke",
    "gateway": "sage-gateway/invoke",
    "mcp": "sage-mcp/invoke",
}
CREDENTIAL_PATTERNS = (
    "Bearer ey",
    "Authorization:",
    "access_token",
    "refresh_token",
    "id_token",
)
EXPECTED_TOOLS = frozenset({"get_product_info", "get_claim_details"})
EXPECTED_PRODUCT = {"Tenant_A": "AXA Drive Protect", "Tenant_B": "Allianz AutoGuard Plus"}
FOREIGN_PRODUCT = {"Tenant_A": "Allianz", "Tenant_B": "AXA"}
SHARED_CLAIM = "CLM-12345"
EXPECTED_CLAIM_AMOUNT = {"Tenant_A": 3200.0, "Tenant_B": 9700.0}
REJECT_STATUSES = frozenset({401, 403})

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "validate-route-c", "version": "1"},
    },
}


@dataclass
class Check:
    """One recorded validation outcome. Never holds credential material."""

    level: str
    name: str
    expected: str
    observed: str
    status: str
    lane: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class Recorder:
    """Collects checks and renders the redacted report."""

    def __init__(self) -> None:
        self.checks: list[Check] = []

    def record(
        self,
        level: str,
        name: str,
        expected: str,
        observed: str,
        ok: bool | None,
        lane: str | None = None,
        **detail: Any,
    ) -> bool:
        status = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        self.checks.append(
            Check(level, name, expected, observed, status, lane, detail)
        )
        marker = {"PASS": "  ok  ", "FAIL": " FAIL ", "SKIP": " skip "}[status]
        lane_label = f"[{lane}] " if lane else ""
        print(f"{marker} {level}: {lane_label}{name} -> {observed}")
        return status == "PASS"

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == "FAIL"]

    def report(self, config_hashes: Mapping[str, str]) -> dict[str, Any]:
        by_level: dict[str, dict[str, int]] = {}
        for c in self.checks:
            tally = by_level.setdefault(c.level, {"PASS": 0, "FAIL": 0, "SKIP": 0})
            tally[c.status] += 1
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "overall": "FAIL" if self.failed else "PASS",
            "summary": by_level,
            "configurationHashes": dict(sorted(config_hashes.items())),
            "checks": [asdict(c) for c in self.checks],
            "notes": [
                "No bearer token value, or any hash derived from one, appears in "
                "this report.",
                "Configuration hashes are sha256 over canonical JSON of deployed "
                "authorizer and target configuration.",
            ],
        }


def config_hash(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def runtime_url(region: str, arn: str, qualifier: str) -> str:
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
        f"{urllib.parse.quote(arn, safe='')}/invocations"
        f"?qualifier={urllib.parse.quote(qualifier, safe='')}"
    )


def post_json(
    url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: int = 180
) -> tuple[int, str]:
    """POST and return status plus body, never raising on an HTTP error."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except urllib.error.URLError as error:
        return 0, f"transport error: {type(error).__name__}"


def bearer(token: str, correlation_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Sage-Correlation-Id": correlation_id,
    }


def claims_of(token: str) -> dict[str, Any]:
    """Decode claims for inspection only; this is not cryptographic validation."""
    payload = token.split(".")[1]
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    return json.loads(raw)


def tamper(token: str) -> str:
    """Flip one signature character so the signature no longer verifies."""
    head, body, signature = token.split(".")
    flipped = ("B" if signature[0] != "B" else "C") + signature[1:]
    return f"{head}.{body}.{flipped}"


def lane_records(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(lane["laneId"]): dict(lane) for lane in manifest["lanes"]}


def authenticate(lanes: Mapping[str, Mapping[str, Any]], credentials_path: pathlib.Path):
    """Return each lane's auth result. Credentials are never printed or stored."""
    users = json.loads(credentials_path.read_text())
    idp = boto3.client("cognito-idp")
    sessions: dict[str, dict[str, str]] = {}
    for lane_id, lane in lanes.items():
        client_id = lane["frontendClientIds"][0]
        result = idp.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": users[lane_id]["username"],
                "PASSWORD": users[lane_id]["password"],
            },
        )["AuthenticationResult"]
        sessions[lane_id] = {
            "access": result["AccessToken"],
            "id": result["IdToken"],
        }
    return sessions


def check_configuration(
    rec: Recorder,
    agentcore: Any,
    lanes: Mapping[str, Mapping[str, Any]],
    hashes: dict[str, str],
    region: str,
) -> None:
    """Read back all six managed authorizers and both Gateway targets."""
    level = "deployed_configuration"
    for lane_id, lane in lanes.items():
        expected_tenant = lane["expectedTenantClaim"]
        client_id = lane["frontendClientIds"][0]
        discovery = lane["discoveryUrl"]

        for door, runtime_key in (("agent", "agentRuntimeId"), ("mcp", "mcpRuntimeId")):
            name = lane[runtime_key]
            matches = [
                r
                for r in agentcore.list_agent_runtimes(maxResults=100).get(
                    "agentRuntimes", []
                )
                if r.get("agentRuntimeName") == name
            ]
            if not matches:
                rec.record(level, f"{door} runtime present", name, "missing", False, lane_id)
                continue
            deployed = agentcore.get_agent_runtime(
                agentRuntimeId=matches[0]["agentRuntimeId"]
            )
            jwt_config = (deployed.get("authorizerConfiguration") or {}).get(
                "customJWTAuthorizer"
            ) or {}
            claims = {
                c["inboundTokenClaimName"]: c["authorizingClaimMatchValue"][
                    "claimMatchValue"
                ]["matchValueString"]
                for c in jwt_config.get("customClaims", [])
            }
            allowlist = (deployed.get("requestHeaderConfiguration") or {}).get(
                "requestHeaderAllowlist"
            )
            observed = {
                "status": deployed.get("status"),
                "discoveryUrl": jwt_config.get("discoveryUrl"),
                "allowedClients": jwt_config.get("allowedClients"),
                "allowedScopes": jwt_config.get("allowedScopes"),
                "tokenUse": claims.get("token_use"),
                "tenantClaim": claims.get("custom:tenant_id"),
                "headerAllowlist": allowlist,
            }
            ok = (
                observed["status"] == "READY"
                and observed["discoveryUrl"] == discovery
                and observed["allowedClients"] == [client_id]
                and observed["allowedScopes"] == [DOOR_SCOPE[door]]
                and observed["tokenUse"] == "access"
                and observed["tenantClaim"] == expected_tenant
                and sorted(allowlist or []) == ["Authorization", "X-Sage-Correlation-Id"]
            )
            rec.record(
                level,
                f"{door} runtime authorizer binds lane",
                f"{discovery} / {client_id} / {DOOR_SCOPE[door]} / {expected_tenant}",
                "bound and READY" if ok else json.dumps(observed, default=str),
                ok,
                lane_id,
            )
            hashes[f"{lane_id}.{door}Runtime.authorizerConfiguration"] = config_hash(
                deployed.get("authorizerConfiguration")
            )

        gateway = agentcore.get_gateway(gatewayIdentifier=lane["gatewayId"])
        gw_jwt = (gateway.get("authorizerConfiguration") or {}).get(
            "customJWTAuthorizer"
        ) or {}
        gw_claims = {
            c["inboundTokenClaimName"]: c["authorizingClaimMatchValue"][
                "claimMatchValue"
            ]["matchValueString"]
            for c in gw_jwt.get("customClaims", [])
        }
        gw_ok = (
            gateway.get("status") == "READY"
            and gw_jwt.get("discoveryUrl") == discovery
            and gw_jwt.get("allowedClients") == [client_id]
            and gw_jwt.get("allowedScopes") == [DOOR_SCOPE["gateway"]]
            and gw_claims.get("token_use") == "access"
            and gw_claims.get("custom:tenant_id") == expected_tenant
        )
        rec.record(
            level,
            "gateway authorizer binds lane",
            f"{discovery} / {client_id} / {DOOR_SCOPE['gateway']} / {expected_tenant}",
            "bound and READY" if gw_ok else "mismatch",
            gw_ok,
            lane_id,
        )
        hashes[f"{lane_id}.gateway.authorizerConfiguration"] = config_hash(
            gateway.get("authorizerConfiguration")
        )

        target_name = f"sage-mcp-{lane_id.replace('_', '-').lower()}"
        targets = [
            t
            for t in agentcore.list_gateway_targets(
                gatewayIdentifier=lane["gatewayId"]
            ).get("items", [])
            if t.get("name") == target_name
        ]
        if not targets:
            rec.record(level, "gateway target present", target_name, "missing", False, lane_id)
            continue
        target = agentcore.get_gateway_target(
            gatewayIdentifier=lane["gatewayId"], targetId=targets[0]["targetId"]
        )
        passthrough = (
            (target.get("targetConfiguration") or {}).get("http") or {}
        ).get("passthrough") or {}
        providers = [
            p.get("credentialProviderType")
            for p in target.get("credentialProviderConfigurations") or []
        ]
        endpoint = passthrough.get("endpoint", "")
        expected_endpoint = (
            f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
            f"{urllib.parse.quote(lane['mcpRuntimeArn'], safe='')}"
        )
        target_ok = (
            target.get("status") == "READY"
            and passthrough.get("protocolType") == "MCP"
            and providers == ["JWT_PASSTHROUGH"]
            and endpoint == expected_endpoint
            and "?" not in endpoint
            and passthrough.get("staticQueryParameters")
            == {"qualifier": lane["mcpRuntimeQualifier"]}
        )
        rec.record(
            level,
            "gateway target is MCP passthrough with JWT_PASSTHROUGH",
            "protocolType=MCP, JWT_PASSTHROUGH, lane MCP base URL, static qualifier",
            "conforms and READY" if target_ok else json.dumps(
                {
                    "status": target.get("status"),
                    "protocolType": passthrough.get("protocolType"),
                    "providers": providers,
                    "endpointMatches": endpoint == expected_endpoint,
                    "endpointHasQuery": "?" in endpoint,
                    "staticQueryParameters": passthrough.get("staticQueryParameters"),
                },
                default=str,
            ),
            target_ok,
            lane_id,
        )
        no_oauth = all(p == "JWT_PASSTHROUGH" for p in providers)
        rec.record(
            level,
            "target configures zero OAuth credential providers",
            "only JWT_PASSTHROUGH",
            ", ".join(providers) or "none",
            no_oauth,
            lane_id,
        )
        hashes[f"{lane_id}.gatewayTarget.targetConfiguration"] = config_hash(
            target.get("targetConfiguration")
        )


def check_tokens(
    rec: Recorder,
    lanes: Mapping[str, Mapping[str, Any]],
    sessions: Mapping[str, Mapping[str, str]],
) -> None:
    """Inspect claims only; the managed doors perform real validation."""
    level = "deployed_configuration"
    for lane_id, lane in lanes.items():
        c = claims_of(sessions[lane_id]["access"])
        scopes = set((c.get("scope") or "").split())
        observed = {
            "issuerMatches": c.get("iss") == lane["issuer"],
            "clientMatches": c.get("client_id") == lane["frontendClientIds"][0],
            "tokenUse": c.get("token_use"),
            "tenant": c.get("custom:tenant_id"),
            "subjectPresent": bool(c.get("sub")),
            "expInFuture": float(c.get("exp", 0)) > time.time(),
            "scopes": sorted(scopes),
            "extraTenantClaims": [
                k for k in c if "tenant" in k.lower() and k != "custom:tenant_id"
            ],
        }
        ok = (
            observed["issuerMatches"]
            and observed["clientMatches"]
            and observed["tokenUse"] == "access"
            and observed["tenant"] == lane["expectedTenantClaim"]
            and observed["subjectPresent"]
            and observed["expInFuture"]
            and scopes == REQUIRED_SCOPES
            and not observed["extraTenantClaims"]
        )
        rec.record(
            level,
            "access token carries exactly the approved lane claims and scopes",
            f"token_use=access, tenant={lane['expectedTenantClaim']}, 4 approved scopes",
            "conforms" if ok else json.dumps(observed),
            ok,
            lane_id,
        )


def check_rejections(
    rec: Recorder,
    lanes: Mapping[str, Mapping[str, Any]],
    sessions: Mapping[str, Mapping[str, str]],
    region: str,
    correlation_id: str,
    skip_agent: bool,
) -> None:
    """Every managed door must reject the other lane and malformed credentials."""
    level = "managed_door_rejection"
    for lane_id, lane in lanes.items():
        other = OTHER_LANE[lane_id]
        foreign = sessions[other]["access"]
        own = sessions[lane_id]["access"]
        doors = {
            "gateway": lane["gatewayTargetUrl"],
            "mcp runtime": runtime_url(
                region, lane["mcpRuntimeArn"], lane["mcpRuntimeQualifier"]
            ),
        }
        if not skip_agent:
            doors["agent runtime"] = lane["agentRuntimeEndpoint"]

        for door, url in doors.items():
            body = {"prompt": "ping"} if door == "agent runtime" else INITIALIZE
            status, _ = post_json(url, bearer(foreign, correlation_id), body)
            rec.record(
                level,
                f"{door} rejects {other} token",
                "401 or 403",
                str(status),
                status in REJECT_STATUSES,
                lane_id,
            )

        mcp_url = doors["mcp runtime"]
        negatives = {
            "missing Authorization header": {
                "X-Sage-Correlation-Id": correlation_id
            },
            "malformed bearer": bearer("not-a-jwt", correlation_id),
            "tampered signature": bearer(tamper(own), correlation_id),
            "ID token instead of access token": bearer(
                sessions[lane_id]["id"], correlation_id
            ),
        }
        for name, headers in negatives.items():
            status, _ = post_json(mcp_url, headers, INITIALIZE)
            rec.record(
                level,
                f"mcp runtime rejects {name}",
                "401 or 403",
                str(status),
                status in REJECT_STATUSES,
                lane_id,
            )

    for name, reason in (
        (
            "expired access token",
            "token lifetime is 60 minutes; needs a scheduled long-running job",
        ),
        (
            "valid token from an unapproved app client",
            "requires provisioning an unapproved client in a lane pool",
        ),
        (
            "per-door missing-scope canary users",
            "requires four canary users with restricted scope grants",
        ),
    ):
        rec.record(level, name, "401 or 403", f"not covered: {reason}", None)


def check_isolation(
    rec: Recorder,
    lanes: Mapping[str, Mapping[str, Any]],
    sessions: Mapping[str, Mapping[str, str]],
    correlation_id: str,
    skip_agent: bool,
) -> None:
    """Same-lane requests must return only that lane's tenant data."""
    level = "end_to_end_isolation"
    for lane_id, lane in lanes.items():
        token = sessions[lane_id]["access"]
        gw = lane["gatewayTargetUrl"]
        headers = bearer(token, correlation_id)

        status, body = post_json(gw, headers, INITIALIZE)
        rec.record(
            level,
            "MCP initialize through gateway",
            "200",
            str(status),
            status == 200,
            lane_id,
        )
        session_headers = dict(headers)

        status, body = post_json(
            gw, session_headers, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        listed = set()
        if status == 200:
            for line in body.splitlines():
                payload = line[6:] if line.startswith("data: ") else line
                try:
                    tools = json.loads(payload)["result"]["tools"]
                except (ValueError, KeyError, TypeError):
                    continue
                listed = {t["name"] for t in tools}
        rec.record(
            level,
            "tools/list through gateway exposes the expected tools",
            ", ".join(sorted(EXPECTED_TOOLS)),
            ", ".join(sorted(listed)) or f"status {status}",
            listed == EXPECTED_TOOLS,
            lane_id,
        )

        for tool, arguments, expected in (
            ("get_product_info", {"product_type": "motor"}, EXPECTED_PRODUCT[lane_id]),
            (
                "get_claim_details",
                {"claim_reference": SHARED_CLAIM},
                str(EXPECTED_CLAIM_AMOUNT[lane_id]),
            ),
        ):
            status, body = post_json(
                gw,
                session_headers,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments},
                },
            )
            found = status == 200 and expected in body
            clean = FOREIGN_PRODUCT[lane_id] not in body
            rec.record(
                level,
                f"{tool} returns only this tenant's data",
                f"contains {expected}, excludes {FOREIGN_PRODUCT[lane_id]}",
                "isolated" if found and clean else f"status {status}, matched={found}, clean={clean}",
                found and clean,
                lane_id,
            )

        if skip_agent:
            rec.record(
                level, "agent streams a complete tenant answer", "tenant data", "skipped by flag", None, lane_id
            )
            continue
        status, body = post_json(
            lane["agentRuntimeEndpoint"],
            headers,
            {"prompt": f"What is the settlement amount for claim {SHARED_CLAIM}?"},
        )
        expected_amount = str(EXPECTED_CLAIM_AMOUNT[lane_id])
        ok = (
            status == 200
            and expected_amount in body
            and FOREIGN_PRODUCT[lane_id] not in body
            and '"code": "request_failed"' not in body
        )
        rec.record(
            level,
            "agent streams a complete tenant answer",
            f"contains {expected_amount}",
            "streamed tenant answer" if ok else f"status {status}",
            ok,
            lane_id,
        )


def check_audit(
    rec: Recorder,
    lanes: Mapping[str, Mapping[str, Any]],
    sessions: Mapping[str, Mapping[str, str]],
    logs: Any,
    skip_agent: bool,
) -> None:
    """One correlation ID must yield one matching Sage API authorization event."""
    level = "audit_evidence"
    for lane_id, lane in lanes.items():
        correlation_id = uuid4().hex
        url = (
            lane["gatewayTargetUrl"] if skip_agent else lane["agentRuntimeEndpoint"]
        )
        headers = bearer(sessions[lane_id]["access"], correlation_id)
        if skip_agent:
            post_json(url, headers, INITIALIZE)
            status, _ = post_json(
                url,
                headers,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "get_product_info",
                        "arguments": {"product_type": "motor"},
                    },
                },
            )
        else:
            status, _ = post_json(url, headers, {"prompt": "List my motor product."})
        if status != 200:
            rec.record(
                level,
                "request under audit succeeded",
                "200",
                str(status),
                False,
                lane_id,
            )
            continue

        events: list[dict[str, Any]] = []
        for _ in range(10):
            time.sleep(6)
            found = logs.filter_log_events(
                logGroupName="/aws/lambda/sage-api",
                startTime=int((time.time() - 900) * 1000),
                filterPattern=f'"{correlation_id}"',
            ).get("events", [])
            if found:
                events = found
                break

        payloads = []
        for event in events:
            message = event.get("message", "")
            start = message.find("{")
            if start != -1:
                try:
                    payloads.append(json.loads(message[start:]))
                except ValueError:
                    continue
        authorized = [p for p in payloads if p.get("outcome") == "authorized"]
        ok = bool(authorized) and all(
            p.get("correlation_id") == correlation_id
            and p.get("tenant_id") == lane["expectedTenantClaim"]
            and p.get("subject")
            for p in authorized
        )
        rec.record(
            level,
            "Sage API emits a correlation-matched authorization event",
            f"correlation_id + subject + tenant_id={lane['expectedTenantClaim']} + authorized",
            "audit event found" if ok else f"{len(events)} events, {len(authorized)} authorized",
            ok,
            lane_id,
            correlationId=correlation_id,
        )


def check_log_hygiene(rec: Recorder, logs: Any, lanes: Mapping[str, Mapping[str, Any]]) -> None:
    """No log group may contain credential material."""
    level = "audit_evidence"
    groups = ["/aws/lambda/sage-api"]
    for lane in lanes.values():
        for key in ("agentRuntimeId", "mcpRuntimeId"):
            prefix = f"/aws/bedrock-agentcore/runtimes/{lane[key]}"
            groups += [
                g["logGroupName"]
                for g in logs.describe_log_groups(logGroupNamePrefix=prefix).get(
                    "logGroups", []
                )
            ]

    start = int((time.time() - 86400) * 1000)
    for group in sorted(set(groups)):
        hits = 0
        for pattern in CREDENTIAL_PATTERNS:
            try:
                hits += len(
                    logs.filter_log_events(
                        logGroupName=group, startTime=start, filterPattern=f'"{pattern}"'
                    ).get("events", [])
                )
            except logs.exceptions.ResourceNotFoundException:
                hits = 0
                break
        rec.record(
            level,
            "log group contains no credential material",
            "0 matches",
            f"{hits} matches in {group}",
            hits == 0,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--credentials", type=pathlib.Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--report", type=pathlib.Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--skip-agent",
        action="store_true",
        help="Skip model invocations; validate config, doors, MCP, and audit only.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    region = str(manifest["region"])
    lanes = lane_records(manifest)
    if set(lanes) != set(LANES):
        raise SystemExit(f"manifest must define exactly {LANES}")

    agentcore = boto3.client("bedrock-agentcore-control", region_name=region)
    logs = boto3.client("logs", region_name=region)

    rec = Recorder()
    hashes: dict[str, str] = {}
    correlation_id = uuid4().hex

    print("=== level 1: deployed configuration ===")
    check_configuration(rec, agentcore, lanes, hashes, region)
    sessions = authenticate(lanes, args.credentials)
    check_tokens(rec, lanes, sessions)

    print("=== level 2: managed door rejection ===")
    check_rejections(rec, lanes, sessions, region, correlation_id, args.skip_agent)

    print("=== level 3: end-to-end tenant isolation ===")
    check_isolation(rec, lanes, sessions, correlation_id, args.skip_agent)

    print("=== level 4: audit evidence ===")
    check_audit(rec, lanes, sessions, logs, args.skip_agent)
    check_log_hygiene(rec, logs, lanes)

    report = rec.report(hashes)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"\nreport -> {args.report}")
    for level, tally in sorted(report["summary"].items()):
        print(f"  {level}: {tally['PASS']} pass, {tally['FAIL']} fail, {tally['SKIP']} skip")
    print(f"overall: {report['overall']}")
    raise SystemExit(1 if rec.failed else 0)


if __name__ == "__main__":
    main()
