import { useCallback, useRef, useState } from "react";
import { ChatInterface } from "@/components/ChatInterface";
import { LoginScreen } from "@/components/LoginScreen";
import {
  hasSameAuthenticationIdentity,
  signOutUser,
  TENANT_DISPLAY_NAMES,
  type AuthSession,
} from "@/lib/auth/cognito";

export function App() {
  const [session, setSession] = useState<AuthSession | null>(null);
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
          <button
            onClick={handleSignOut}
            className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-2"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-hidden max-w-3xl w-full mx-auto px-4 py-2 flex flex-col">
        <ChatInterface
          key={session.sessionId}
          session={session}
          onSessionRenewed={handleSessionRenewed}
          onSessionTerminated={handleSessionTerminated}
        />
      </main>
    </div>
  );
}

export default App;
