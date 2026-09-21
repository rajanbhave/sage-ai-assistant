import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  authenticateUser,
  TENANT_DISPLAY_NAMES,
  type AuthSession,
  type LaneId,
} from "@/lib/auth/cognito";

interface LoginScreenProps {
  onLogin: (session: AuthSession) => void;
}

const LANES = [
  { value: "Tenant_A", label: TENANT_DISPLAY_NAMES.Tenant_A, defaultUser: "axa-user" },
  { value: "Tenant_B", label: TENANT_DISPLAY_NAMES.Tenant_B, defaultUser: "allianz-user" },
] as const satisfies readonly {
  value: LaneId;
  label: string;
  defaultUser: string;
}[];

export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [laneId, setLaneId] = useState<LaneId>("Tenant_A");
  const [username, setUsername] = useState("axa-user");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleLaneChange = (value: string) => {
    const lane = LANES.find((candidate) => candidate.value === value);
    if (!lane) {
      setError("The selected authentication lane is invalid.");
      return;
    }
    setLaneId(lane.value);
    setUsername(lane.defaultUser);
    setError(null);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      onLogin(await authenticateUser(laneId, username.trim(), password));
    } catch {
      setError("Authentication failed. Verify your lane and credentials.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Sage AI Assistant</h1>
          <p className="text-sm text-muted-foreground">Insurance Suite — sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="lane-select">
              Tenant lane
            </label>
            <select
              id="lane-select"
              value={laneId}
              onChange={(event) => handleLaneChange(event.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {LANES.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="username-input">
              Username
            </label>
            <input
              id="username-input"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="username"
              autoComplete="username"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="password-input">
              Password
            </label>
            <input
              id="password-input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="password"
              autoComplete="current-password"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={isLoading || !password.trim()}>
            {isLoading ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="text-xs text-center text-muted-foreground">
          Demo users: <span className="font-mono">axa-user</span> or{" "}
          <span className="font-mono">allianz-user</span>. Obtain passwords through the approved secret-sharing channel.
        </p>
      </div>
    </div>
  );
}
