"""Stream events must carry only the client contract, never Strands internals.

Strands attaches live objects (the ``Agent`` itself, trace spans, UUIDs) to every
streamed event. Forwarding them raised in the strict field sanitizer and aborted
the whole invocation, so these tests pin both halves of the fix: internals are
dropped, and the rendered contract still survives.
"""

import importlib
import sys
import uuid

import boto3
import pytest

from sage_identity import CorrelationId


class _EmptyRegistry:
    def list_registry_records(self, **_kwargs):
        return {"registryRecords": []}


@pytest.fixture
def agent_module(monkeypatch, request):
    monkeypatch.setenv("GATEWAY_URL", "https://gateway.example/target/invocations")
    monkeypatch.setenv("SKILL_REGISTRY_ID", "registry")
    monkeypatch.setattr(boto3, "client", lambda *_a, **_k: _EmptyRegistry())
    sys.modules.pop("agent.agent", None)
    request.addfinalizer(lambda: sys.modules.pop("agent.agent", None))
    return importlib.import_module("agent.agent")


class _Unserializable:
    """Stands in for the live Strands ``Agent`` attached to every event."""


def test_strands_internals_are_dropped(agent_module):
    correlation_id = CorrelationId.new()

    serialized = agent_module._serialize_stream_event(
        {
            "data": "Hello",
            "delta": {"text": "Hello"},
            "agent": _Unserializable(),
            "event_loop_cycle_id": uuid.uuid4(),
            "event_loop_cycle_trace": _Unserializable(),
            "event_loop_cycle_span": _Unserializable(),
            "request_state": {"seen": True},
        },
        correlation_id,
    )

    assert serialized == {"data": "Hello", "delta": {"text": "Hello"}}


def test_terminal_stop_reason_is_projected(agent_module):
    class _Result:
        stop_reason = "end_turn"

    serialized = agent_module._serialize_stream_event(
        {"result": _Result()}, CorrelationId.new()
    )

    assert serialized == {"result": {"stop_reason": "end_turn"}}


def test_tool_use_and_tool_result_contract_survives(agent_module):
    event = {
        "current_tool_use": {"toolUseId": "t-1", "name": "get_product_info"},
        "delta": {"toolUse": {"input": ""}},
        "agent": _Unserializable(),
    }
    assert agent_module._serialize_stream_event(event, CorrelationId.new()) == {
        "current_tool_use": {"toolUseId": "t-1", "name": "get_product_info"},
        "delta": {"toolUse": {"input": ""}},
    }

    message = {
        "message": {
            "role": "user",
            "content": [
                {"toolResult": {"toolUseId": "t-1", "content": [{"text": "{}"}]}}
            ],
        },
        "event_loop_cycle_span": _Unserializable(),
    }
    assert agent_module._serialize_stream_event(message, CorrelationId.new()) == {
        "message": message["message"]
    }


def test_internal_only_event_serializes_empty(agent_module):
    """An internals-only event yields nothing rather than aborting the stream."""
    assert (
        agent_module._serialize_stream_event(
            {"agent": _Unserializable(), "event_loop_cycle_id": uuid.uuid4()},
            CorrelationId.new(),
        )
        == {}
    )
