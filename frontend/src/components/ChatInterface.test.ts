import { describe, expect, it } from "vitest";
import { AuthenticationArtifact } from "@/lib/auth/artifact";
import { applyStreamEvent, matchesInvocationBinding, type Message } from "./ChatInterface";
import type { InvocationBinding } from "@/lib/agentcore-client/client";
import type { AuthSession } from "@/lib/auth/cognito";

const session: AuthSession = {
  lane: { laneId: "Tenant_A", tenantId: "Tenant_A", userPoolId: "pool", appClientId: "client", issuer: "issuer", agentRuntimeEndpoint: "https://agent", expectedTenantClaim: "Tenant_A" },
  accessToken: new AuthenticationArtifact("token"), subject: "subject", tenantId: "Tenant_A", expiresAt: 4_000_000_000, sessionId: "session", username: "user",
  claims: { issuer: "issuer", clientId: "client", tokenUse: "access", subject: "subject", tenantId: "Tenant_A", scopes: ["sage-agent/invoke"], expiresAt: 4_000_000_000, tokenId: "jti" },
};
const binding: InvocationBinding = { sessionId: "session", laneId: "Tenant_A", subject: "subject", tenantId: "Tenant_A", correlationId: "c" };
const initial: Message[] = [{ id: "assistant", role: "assistant", segments: [], isStreaming: true }];

describe("conversation binding", () => {
  it("rejects late events and accepts sanitized current events", () => {
    expect(matchesInvocationBinding(session, binding)).toBe(true);
    const late = { ...binding, sessionId: "old" } as InvocationBinding;
    expect(applyStreamEvent(initial, "assistant", { type: "text", content: "late" }, session, late)).toBe(initial);
    const updated = applyStreamEvent(initial, "assistant", { type: "text", content: "hello" }, session, binding);
    expect(updated[0]?.segments).toEqual([{ type: "text", content: "hello" }]);
  });
});
