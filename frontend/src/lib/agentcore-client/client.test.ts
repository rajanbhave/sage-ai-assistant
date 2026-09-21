import { describe, expect, it, vi } from "vitest";
import { AuthenticationArtifact } from "@/lib/auth/artifact";
import { createCorrelationId, invokeAgent } from "./client";

const response = (lines: string[]) => new Response(lines.join("\n"), { status: 200, headers: { "Content-Type": "text/event-stream" } });

describe("Agent transport", () => {
  it("creates a compact backend-compatible correlation ID", () => {
    expect(createCorrelationId()).toMatch(/^[0-9a-f]{32}$/);
  });

  it("sends one original bearer and emits unbound stream events", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(["data: {\"result\":{\"stop_reason\":\"end_turn\"}}"]));
    vi.stubGlobal("fetch", fetchMock);
    const events: unknown[] = [];
    await invokeAgent("hello", {
      endpoint: "https://agent.example/invocations",
      accessToken: new AuthenticationArtifact("original"),
      binding: { sessionId: "s", laneId: "Tenant_A", subject: "u", tenantId: "Tenant_A", correlationId: "d".repeat(32) },
    }, event => events.push(event), new AbortController().signal);
    const request = fetchMock.mock.calls[0]?.[1];
    expect(request.headers.Authorization).toBe("Bearer original");
    expect(request.headers["X-Sage-Correlation-Id"]).toBe("d".repeat(32));
    expect(events[0]).toEqual({ type: "result", stopReason: "end_turn" });
  });

  it("stops an expired SSE invocation without replaying it", async () => {
    const correlationId = "e".repeat(32);
    const fetchMock = vi.fn().mockResolvedValue(response([
      `data: ${JSON.stringify({ code: "session_expired", correlation_id: correlationId })}`,
    ]));
    vi.stubGlobal("fetch", fetchMock);

    await expect(invokeAgent("hello", {
      endpoint: "https://agent.example/invocations",
      accessToken: new AuthenticationArtifact("expired"),
      binding: { sessionId: "s", laneId: "Tenant_A", subject: "u", tenantId: "Tenant_A", correlationId },
    }, vi.fn(), new AbortController().signal)).rejects.toEqual(
      expect.objectContaining({
        name: "AgentInvocationError",
        code: "session_expired",
        message: "The session has expired.",
      })
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
