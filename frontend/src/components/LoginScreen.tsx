import { useState } from "react";
import { Button } from "@/components/ui/button";
import { authenticateUser, type AuthSession } from "@/lib/auth/cognito";

interface LoginScreenProps {
  onLogin: (session: AuthSession) => void;
}

const TENANTS = [
  { value: "axa", label: "AXA", defaultUser: "axa-user" },
  { value: "allianz", label: "Allianz", defaultUser: "allianz-user" },
] as const;

export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [tenantId, setTenantId] = useState<string>("axa");
  const [username, setUsername] = useState("axa-user");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleTenantChange = (value: string) => {
    setTenantId(value);
    const tenant = TENANTS.find((t) => t.value === value);
    if (tenant) setUsername(tenant.defaultUser);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const session = await authenticateUser(tenantId, username.trim(), password);
      onLogin(session);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Authentication failed";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Header */}
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Sage AI Assistant</h1>
          <p className="text-sm text-muted-foreground">Insurance Suite — sign in to continue</p>
        </div>

        {/* Login form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Tenant selector */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="tenant-select">
              Tenant
            </label>
            <select
              id="tenant-select"
              value={tenantId}
              onChange={(e) => handleTenantChange(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {TENANTS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {/* Username */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="username-input">
              Username
            </label>
            <input
              id="username-input"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="username"
              autoComplete="username"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="password-input">
              Password
            </label>
            <input
              id="password-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="password"
              autoComplete="current-password"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Error */}
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={isLoading || !password.trim()}>
            {isLoading ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        {/* Demo credentials hint */}
        <p className="text-xs text-center text-muted-foreground">
          Demo: <span className="font-mono">axa-user / AXApassword1</span> or{" "}
          <span className="font-mono">allianz-user / Allianzpassword1</span>
        </p>
      </div>
    </div>
  );
}
