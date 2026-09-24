import { buildAuthorizationHeader } from "@/lib/auth/artifact";
import { resolveTrustedLane, type AuthSession, type LaneId } from "@/lib/auth/cognito";
import { createCorrelationId } from "@/lib/agentcore-client/client";
import { DEMO_STAGE_ENABLED } from "./config";

/**
 * Deliberate cross-lane rejection probe, for demonstration builds only.
 *
 * This is the one place in the frontend that intentionally sends the session
 * bearer to an endpoint other than the selected lane's Agent Runtime. It exists
 * to show a live managed denial, and it is refused unless the build explicitly
 * enabled the demo stage.
 */

export interface CrossLaneProbeResult {
  readonly targetLaneId: LaneId;
  readonly correlationId: string;
  /** HTTP status returned by the other lane, or null when the request failed. */
  readonly status: number | null;
  /** True when the other lane denied the bearer, which is the expected outcome. */
  readonly denied: boolean;
}

function otherLaneId(laneId: LaneId): LaneId {
  return laneId === "Tenant_A" ? "Tenant_B" : "Tenant_A";
}

/** Send the current bearer to the other lane and report only its status. */
export async function probeOtherLane(
  session: AuthSession,
  signal: AbortSignal
): Promise<CrossLaneProbeResult> {
  if (!DEMO_STAGE_ENABLED) {
    throw new Error("The cross-lane probe is available only in demo builds.");
  }

  const targetLaneId = otherLaneId(session.lane.laneId);
  const target = resolveTrustedLane(targetLaneId);
  const correlationId = createCorrelationId();

  try {
    const response = await fetch(target.agentRuntimeEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: buildAuthorizationHeader(session.accessToken),
        "X-Sage-Correlation-Id": correlationId,
      },
      body: JSON.stringify({ prompt: "cross-lane rejection probe" }),
      signal,
    });

    // The response body is never read: a denial is proven by the status, and an
    // unexpected success must not place another lane's content on screen.
    return {
      targetLaneId,
      correlationId,
      status: response.status,
      denied: response.status === 401 || response.status === 403,
    };
  } catch {
    return { targetLaneId, correlationId, status: null, denied: false };
  }
}
