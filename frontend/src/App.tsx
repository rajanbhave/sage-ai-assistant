import { useState } from "react";
import { ChatInterface } from "@/components/ChatInterface";
import { TenantSelector } from "@/components/TenantSelector";

export function App() {
  const [tenantId, setTenantId] = useState<string>("axa");

  return (
    <div className="flex flex-col h-screen bg-background text-foreground">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold tracking-tight">Sage AI Assistant</span>
          <span className="text-xs text-muted-foreground">Insurance Suite</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Tenant:</span>
          <TenantSelector tenantId={tenantId} onTenantChange={setTenantId} />
        </div>
      </header>

      {/* Main chat area */}
      <main className="flex-1 overflow-hidden max-w-3xl w-full mx-auto px-4 py-2 flex flex-col">
        <ChatInterface tenantId={tenantId} />
      </main>
    </div>
  );
}

export default App;
