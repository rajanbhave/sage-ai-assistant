"""Steady demo traffic for the Instances lanes, so Attribute has per-tenant Bedrock usage to show.

Bluepine (Tenant_A) gets about three times Oakhaven's (Tenant_B) volume. Each lane uses one pinned
runtime session, so all traffic lands on one warm EC2 instance per lane.

    uv run python -m infra.instances.traffic --once            # go/no-go: one call per lane
    uv run python -m infra.instances.traffic --hours 48 --per-hour 40
"""

from __future__ import annotations

import argparse
import json
import random
import time
import uuid
from pathlib import Path

from scripts.validate_route_c import DEFAULT_CREDENTIALS, DEFAULT_MANIFEST, authenticate, bearer, lane_records, post_json

HERE = Path(__file__).parent
WEIGHTS = {"Tenant_A": 3, "Tenant_B": 1}
TOKEN_REFRESH_SECONDS = 45 * 60  # access tokens are valid for 60 minutes
PROMPTS = [
    "What does my motor product cover?",
    "What is the settlement amount for claim CLM-12345?",
    "Summarise the status of claim CLM-12345 and what happens next.",
    "Is theft covered under my motor policy, and what is the excess?",
    "Compare third-party liability and own damage cover for my product.",
    "Draft a short, friendly update to the customer on claim CLM-12345.",
    "What documents are still missing for claim CLM-12345?",
    "Explain the base premium of my motor product in plain language.",
]


def session_id(lane: str) -> str:
    """Stable per lane and at least 33 characters, as AgentCore requires."""
    return f"sage-reinvent-{lane.lower().replace('_', '-')}-pinned-session-0001"


def outcome(status: int, body: str) -> str:
    """'ok' only when the agent streamed an answer; otherwise a short, non-secret reason.

    The agent reports identity and request failures inside an HTTP 200 stream, so status alone is not enough.
    """
    if status != 200:
        return f"http_{status}"
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            try:
                events.append(json.loads(line[5:]))
            except ValueError:
                continue
    for event in events:
        if isinstance(event, dict) and "code" in event and "correlation_id" in event:
            return f"stream_error_{event['code']}"  # stable error code only, never the message body
    has_text = any(isinstance(e, dict) and "text" in json.dumps(e.get("event", {}).get("contentBlockDelta", {})) for e in events)
    return "ok" if has_text else "no_answer"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="one call per lane, then exit")
    p.add_argument("--hours", type=float, default=48)
    p.add_argument("--per-hour", type=int, default=40, help="total calls per hour across lanes")
    p.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    p.add_argument("--log", type=Path, default=HERE / "traffic_log.jsonl")
    args = p.parse_args()

    urls = {lane: r["invocationUrl"] for lane, r in json.loads((HERE / "instances_output.json").read_text()).items()}
    lanes = lane_records(json.loads(DEFAULT_MANIFEST.read_text()))
    for lane in urls:
        print(f"VITE_TENANT_{lane[-1]}_RUNTIME_SESSION_ID={session_id(lane)}")

    def call(lane: str, tokens: dict) -> None:
        prompt = random.choice(PROMPTS)
        headers = {**bearer(tokens[lane]["access"], uuid.uuid4().hex),
                   "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id(lane)}
        started = time.time()
        status, body = post_json(urls[lane], headers, {"prompt": prompt}, timeout=600)
        record = {"ts": round(started), "lane": lane, "status": status,
                  "seconds": round(time.time() - started, 1), "prompt": prompt, "outcome": outcome(status, body)}
        print(json.dumps(record))
        with args.log.open("a") as f:
            f.write(json.dumps(record) + "\n")

    tokens, issued = authenticate({k: lanes[k] for k in urls}, args.credentials), time.time()
    if args.once:
        for lane in urls:
            call(lane, tokens)
        return

    deadline = time.time() + args.hours * 3600
    while time.time() < deadline:
        if time.time() - issued > TOKEN_REFRESH_SECONDS:
            tokens, issued = authenticate({k: lanes[k] for k in urls}, args.credentials), time.time()
        call(random.choices(list(WEIGHTS), weights=list(WEIGHTS.values()))[0], tokens)
        time.sleep(random.expovariate(args.per_hour / 3600))


if __name__ == "__main__":
    main()
