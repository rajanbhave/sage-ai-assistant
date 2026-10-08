import { describe, expect, it } from "vitest";
import { graphIsConsistent } from "./graph";
import { initialStageState, stageReducer, type StageState } from "./stage-state";

function apply(
  state: StageState,
  ...events: Parameters<typeof stageReducer>[1][]
): StageState {
  return events.reduce(stageReducer, state);
}

describe("demo stage state", () => {
  it("keeps every edge anchored to a declared node", () => {
    expect(graphIsConsistent()).toBe(true);
  });

  it("lights the managed chain from one accepted agent stream", () => {
    const state = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "agent_accepted" } }
    );

    // A first stream event proves the Gateway accepted the bearer, because the
    // agent lists Gateway tools before streaming. It does not prove the Gateway
    // reached the MCP Runtime, so that stays dark until a tool round-trips.
    for (const node of ["agent", "gateway"]) {
      expect(state.nodeStates[node]).toBe("active");
    }
    expect(state.nodeStates.mcp).toBeUndefined();
    expect(state.nodeStates.api).toBeUndefined();
    expect(state.nodeStates.data).toBeUndefined();
  });

  it("reaches the MCP Runtime only once a tool is actually requested", () => {
    const state = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "agent_accepted" } },
      { kind: "event", event: { type: "tool_started", name: "get_product_info" } }
    );

    expect(state.nodeStates.mcp).toBe("active");
    expect(state.nodeStates.api).toBeUndefined();
  });

  it("only reaches the API and data once a tool result returns", () => {
    const state = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "agent_accepted" } },
      { kind: "event", event: { type: "tool_completed", name: "get_claim_details" } }
    );

    expect(state.nodeStates.api).toBe("active");
    expect(state.nodeStates.data).toBe("active");
    expect(state.nodeStates.agent).toBe("done");
  });

  it("holds a cross-lane denial until the stage is reset", () => {
    const denied = apply(initialStageState, {
      kind: "event",
      event: { type: "cross_lane_rejected", status: 401 },
    });
    expect(denied.nodeStates["other-lane"]).toBe("rejected");
    expect(denied.rejected).toBe(true);

    const afterRun = apply(
      denied,
      { kind: "start" },
      { kind: "event", event: { type: "agent_accepted" } },
      { kind: "event", event: { type: "run_completed" } }
    );
    expect(afterRun.nodeStates["other-lane"]).toBe("rejected");
    expect(afterRun.rejected).toBe(true);

    expect(apply(afterRun, { kind: "reset" })).toEqual(initialStageState);
  });

  it("stops the run and marks failure when the agent rejects the bearer", () => {
    const state = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "run_failed", code: "request_failed" } }
    );

    expect(state.running).toBe(false);
    expect(state.failure).toBe("request_failed");
    expect(state.nodeStates.agent).toBe("failed");
  });
});


describe("in-flight hop", () => {
  it("shows the agent hop in flight before anything has accepted the bearer", () => {
    const state = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "run_started" } }
    );

    // The browser really has dispatched the request, so the hop is visible
    // during the cold-start wait. It must not read as acceptance.
    expect(state.nodeStates.agent).toBe("pending");
    expect(state.edgeStates["browser-agent"]).toBe("pending");
    expect(state.nodeStates.gateway).toBeUndefined();
    expect(state.nodeStates.mcp).toBeUndefined();
  });

  it("promotes the agent to accepted only on the first stream event", () => {
    const state = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "run_started" } },
      { kind: "event", event: { type: "agent_accepted" } }
    );

    expect(state.nodeStates.agent).toBe("active");
    expect(state.nodeStates.gateway).toBe("active");
  });

  it("returns an unproven in-flight hop to idle when the run ends", () => {
    const completed = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "run_started" } },
      { kind: "event", event: { type: "run_completed" } }
    );

    // Nothing ever accepted the bearer, so the hop must not be left claiming
    // success or stuck mid-flight.
    expect(completed.nodeStates.agent).toBe("idle");
    expect(completed.edgeStates["browser-agent"]).toBe("idle");

    const failed = apply(
      initialStageState,
      { kind: "start" },
      { kind: "event", event: { type: "run_started" } },
      { kind: "event", event: { type: "run_failed", code: "request_failed" } },
      { kind: "event", event: { type: "run_completed" } }
    );

    expect(failed.nodeStates.agent).toBe("failed");
    expect(failed.nodeStates.browser).toBe("idle");
  });
});
