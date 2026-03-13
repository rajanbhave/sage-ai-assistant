import type { StreamCallback } from "./types";
import { readSSEStream } from "./utils/sse";
import { parseStrandsChunk } from "./parsers/strands";

const TENANT_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id";

/**
 * Sends a user query to the Sage agent and streams the response.
 *
 * This is the single point where the tenant header and Authorization header
 * are injected into every outbound request.
 *
 * Phase 2: when a ``jwtToken`` is provided it is sent as the
 * ``Authorization: Bearer <token>`` header. The agent extracts
 * ``custom:tenant_id`` from the JWT claims and uses it as the tenant ID,
 * so the ``tenantId`` parameter acts as a UI hint / Phase 1 fallback only.
 *
 * Phase 1 fallback: when no JWT is provided, the static
 * ``VITE_AGENT_BEARER_TOKEN`` env var is used for auth (if set) and the
 * tenant ID is sent via the custom header.
 *
 * @param query - The user's message
 * @param tenantId - The selected tenant identifier (e.g. "axa" or "allianz")
 * @param onEvent - Callback invoked for each parsed StreamEvent
 * @param jwtToken - Optional Phase 2 JWT ID token from Cognito
 */
export async function invokeAgent(
  query: string,
  tenantId: string,
  onEvent: StreamCallback,
  jwtToken?: string
): Promise<void> {
  const agentUrl =
    (import.meta.env.VITE_AGENT_URL as string | undefined) ||
    "http://localhost:8080/invocations";

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    [TENANT_HEADER]: tenantId,
  };

  if (jwtToken) {
    // Phase 2: use the Cognito ID token for auth; agent extracts tenant from claims
    headers["Authorization"] = `Bearer ${jwtToken}`;
  } else {
    // Phase 1 fallback: static bearer token from env
    const bearerToken = import.meta.env.VITE_AGENT_BEARER_TOKEN as string | undefined;
    if (bearerToken) {
      headers["Authorization"] = `Bearer ${bearerToken}`;
    }
  }

  const response = await fetch(agentUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt: query }),
  });

  if (!response.ok) {
    throw new Error(`Agent request failed: ${response.status} ${response.statusText}`);
  }

  await readSSEStream(response, parseStrandsChunk, onEvent);
}
