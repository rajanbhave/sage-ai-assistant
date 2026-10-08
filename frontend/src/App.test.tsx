import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SessionWorkspace } from "./App";
import { AuthenticationArtifact } from "@/lib/auth/artifact";
import type { AuthSession } from "@/lib/auth/cognito";

/**
 * Toggling between chat and the demo stage must not unmount either panel.
 *
 * The original implementation rendered one panel or the other from a ternary, so
 * every toggle destroyed the subtree it left: sending a prompt and switching to
 * the stage lost the conversation, and switching back lost the evidence feed.
 */

const session: AuthSession = {
  lane: {
    laneId: "Tenant_A",
    tenantId: "Tenant_A",
    userPoolId: "pool",
    appClientId: "client",
    issuer: "issuer",
    agentRuntimeEndpoint: "https://agent",
    expectedTenantClaim: "Tenant_A",
  },
  accessToken: new AuthenticationArtifact("token"),
  subject: "subject",
  tenantId: "Tenant_A",
  expiresAt: 4_000_000_000,
  sessionId: "session",
  username: "user",
  claims: {
    issuer: "issuer",
    clientId: "client",
    tokenUse: "access",
    subject: "subject",
    tenantId: "Tenant_A",
    scopes: ["sage-agent/invoke"],
    expiresAt: 4_000_000_000,
    tokenId: "jti",
  },
};

function render(showStage: boolean, demoStageEnabled = true): string {
  return renderToStaticMarkup(
    <SessionWorkspace
      session={session}
      showStage={showStage}
      demoStageEnabled={demoStageEnabled}
      onSessionRenewed={() => {}}
      onSessionTerminated={() => {}}
    />
  );
}

function panelClass(markup: string, testId: string): string | null {
  const match = markup.match(
    new RegExp(`<div class="([^"]*)" data-testid="${testId}"`)
  );
  if (match) return match[1] ?? null;
  const reordered = markup.match(
    new RegExp(`<div data-testid="${testId}" class="([^"]*)"`)
  );
  return reordered?.[1] ?? null;
}

describe("session workspace panels", () => {
  it("keeps both panels mounted in either view", () => {
    for (const showStage of [false, true]) {
      const markup = render(showStage);
      expect(markup).toContain('data-testid="chat-panel"');
      expect(markup).toContain('data-testid="stage-panel"');
    }
  });

  it("hides exactly one panel per view instead of removing it", () => {
    const chatView = render(false);
    expect(panelClass(chatView, "stage-panel")).toBe("hidden");
    expect(panelClass(chatView, "chat-panel")).not.toBe("hidden");

    const stageView = render(true);
    expect(panelClass(stageView, "chat-panel")).toBe("hidden");
    expect(panelClass(stageView, "stage-panel")).not.toBe("hidden");
  });

  it("omits the stage entirely when the demo build flag is off", () => {
    const markup = render(true, false);
    expect(markup).not.toContain('data-testid="stage-panel"');
    expect(panelClass(markup, "chat-panel")).not.toBe("hidden");
  });
});
