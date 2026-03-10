import { useState } from "react";
import { ChatInterface } from "@/components/ChatInterface";
import { TenantSelector } from "@/components/TenantSelector";
import { LoginScreen } from "@/components/LoginScreen";
import { isCognitoConfigured, signOutUser, type AuthSession } from "@/lib/auth/cognito";

const COGNITO_ENABLED = isCognitoConfigured();

export function App() {
  // Phase 1: tenant from dropdown
  const [tenantId, setTenantId] = useState<string>("axa");

  // Phase 2: JWT session from Cognito login
  const [session, setSession] = useState<AuthSession | null>(null);

  // In Phase 2 mode, derive tenantId from the JWT session
  const activeTenantId = COGNITO_ENABLED && session ? session.tenantId : tenantId;

  const handleLogin = (newSession: AuthSession) => {
    setSession(newSession);
  };

  const handleSignOut = () => {
    if (session) {
      signOutUser(session.tenantId, session.username);
      setSession(null);
    }
  };

  // Phase 2: show login screen until authenticated
  if (COGNITO_ENABLED && !session) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <div className="flex flex-col h-screen bg-background text-foreground">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold tracking-tight">Sage AI Assistant</span>
          <span className="text-xs text-muted-foreground">Insurance Suite</span>
        </div>
        <div className="flex items-center gap-3">
          {COGNITO_ENABLED && session ? (
            // Phase 2: show authenticated user + sign out
            <>
              <span className="text-sm text-muted-foreground">
                {session.tenantId.toUpperCase()} — {session.username}
              </span>
              <button
                onClick={handleSignOut}
                className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-2"
              >
                Sign out
              </button>
            </>
          ) : (
            // Phase 1: tenant selector dropdown
            <>
              <span className="text-sm text-muted-foreground">Tenant:</span>
              <TenantSelector tenantId={tenantId} onTenantChange={setTenantId} />
            </>
          )}
        </div>
      </header>

      {/* Main chat area */}
      <main className="flex-1 overflow-hidden max-w-3xl w-full mx-auto px-4 py-2 flex flex-col">
        <ChatInterface
          tenantId={activeTenantId}
          jwtToken={session?.idToken}
        />
      </main>
    </div>
  );
}

export default App;
