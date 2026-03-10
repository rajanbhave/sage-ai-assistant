import type { StreamCallback } from "./types";
import { readSSEStream } from "./utils/sse";
import { parseStrandsChunk } from "./parsers/strands";

const TENANT_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant-Id";

/**
 * Sends a user query to the Sage agent and streams the response.
 *
 * This is the single point where the tenant header is injected into every
 * outbound request. All agent communication goes through this function.
 *
 * @param query - The user's message
 * @param tenantId - The selected tenant identifier (e.g. "axa" or "allianz")
 * @param onEvent - Callback invoked for each parsed StreamEvent
 */
export async function invokeAgent(
  query: string,
  tenantId: string,
  onEvent: StreamCallback
): Promise<void> {
  const agentUrl =
    (import.meta.env.VITE_AGENT_URL as string | undefined) ||
    "http://localhost:8080/invocations";
  const bearerToken = import.meta.env.VITE_AGENT_BEARER_TOKEN as string | undefined;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    [TENANT_HEADER]: tenantId,
  };

  if (bearerToken) {
    headers["Authorization"] = `Bearer ${bearerToken}`;
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
