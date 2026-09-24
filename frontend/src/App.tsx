import { useCallback, useRef, useState } from "react";
import { ChatInterface } from "@/components/ChatInterface";
import { DemoStageApp } from "@/components/DemoStageApp";
import { LoginScreen } from "@/components/LoginScreen";
import { DEMO_STAGE_ENABLED } from "@/lib/demo/config";
import {
  hasSameAuthenticationIdentity,
  signOutUser,
  TENANT_DISPLAY_NAMES,
  type AuthSession,
} from "@/lib/auth/cognito";

interface SessionWorkspaceProps {
  readonly session: AuthSession;
  readonly showStage: boolean;
  readonly onSessionRenewed: (renewed: AuthSession) => void;
  readonly onSessionTerminated: (terminated: AuthSession) => void;
  /** Injectable so tests can exercise the stage without a demo build. */
  readonly demoStageEnabled?: boolean;
}

/**
 * Render the chat and demo-stage panels, toggling visibility rather than mounting.
 *
 * Unmounting either panel discards its React state: switching to the stage would
 * wipe the conversation, and switching back would wipe the witnessed evidence
 * feed. `hidden` sets display:none, which also removes the inactive panel from
 * the accessibility tree and the tab order.
 *
 * `key={session.sessionId}` is retained on both panels, so an identity change
 * still remounts them. That is what clears conversation and stage state when the
 * lane, subject, or tenant changes.
 */
export function SessionWorkspace({
  session,
  showStage,
  onSessionRenewed,
  onSessionTerminated,
  demoStageEnabled = DEMO_STAGE_ENABLED,
}: SessionWorkspaceProps) {
  const stageVisible = demoStageEnabled && showStage;
  return (
    <main className="flex-1 overflow-hidden flex flex-col">
      {demoStageEnabled && (
        <div
          data-testid="stage-panel"
          className={
            stageVisible
              ? "flex-1 overflow-hidden max-w-6xl w-full mx-auto px-4 py-3 flex flex-col"
              : "hidden"
          }
        >
          <DemoStageApp key={session.sessionId} session={session} />
        </div>
      )}
      <div
        data-testid="chat-panel"
        className={
          stageVisible
            ? "hidden"
            : "flex-1 overflow-hidden max-w-3xl w-full mx-auto px-4 py-2 flex flex-col"
        }
      >
        <ChatInterface
          key={session.sessionId}
          session={session}
          onSessionRenewed={onSessionRenewed}
          onSessionTerminated={onSessionTerminated}
        />
      </div>
    </main>
  );
}

export function App() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [showStage, setShowStage] = useState(false);
  const sessionRef = useRef<AuthSession | null>(session);
  sessionRef.current = session;

  const handleSessionRenewed = useCallback((renewed: AuthSession) => {
    const current = sessionRef.current;
    if (
      !current ||
      current.sessionId !== renewed.sessionId ||
      !hasSameAuthenticationIdentity(current, renewed)
    ) {
      return;
    }
    sessionRef.current = renewed;
    setSession(renewed);
  }, []);

  const handleSessionTerminated = useCallback((terminated: AuthSession) => {
    if (sessionRef.current?.sessionId !== terminated.sessionId) return;
    sessionRef.current = null;
    setSession(null);
    signOutUser(terminated);
  }, []);

  const handleSignOut = () => {
    const terminatedSession = sessionRef.current;
    if (!terminatedSession) return;
    sessionRef.current = null;
    setSession(null);
    signOutUser(terminatedSession);
  };

  if (!session) {
    return <LoginScreen onLogin={setSession} />;
  }

  return (
    <div className="flex flex-col h-screen bg-background text-foreground">
      <header className="flex items-center justify-between px-6 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold tracking-tight">Sage AI Assistant</span>
          <span className="text-xs text-muted-foreground">Insurance Suite</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {TENANT_DISPLAY_NAMES[session.tenantId]} — {session.username}
          </span>
          {DEMO_STAGE_ENABLED && (
            <button
              onClick={() => setShowStage((previous) => !previous)}
              className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-2"
            >
              {showStage ? "Chat" : "Demo stage"}
            </button>
          )}
          <button
            onClick={handleSignOut}
            className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-2"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Panels stay mounted; see SessionWorkspace for why. */}
      <SessionWorkspace
        session={session}
        showStage={showStage}
        onSessionRenewed={handleSessionRenewed}
        onSessionTerminated={handleSessionTerminated}
      />
    </div>
  );
}

export default App;
