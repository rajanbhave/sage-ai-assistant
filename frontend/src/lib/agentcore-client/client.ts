import type { LaneId } from "../auth/cognito";
import {
  buildAuthorizationHeader,
  isAuthenticationArtifact,
  type AuthenticationArtifact,
} from "../auth/artifact";
import type { ChunkParser, StreamEvent } from "./types";
import { parseStrandsChunk } from "./parsers/strands";
import { readSSEStream } from "./utils/sse";

const CORRELATION_HEADER = "X-Sage-Correlation-Id";
const CORRELATION_ID_PATTERN = /^[0-9a-f]{32}$/;

/** Create the compact correlation identifier accepted by every backend boundary. */
export function createCorrelationId(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export interface InvocationBinding {
  readonly sessionId: string;
  readonly laneId: LaneId;
  readonly subject: string;
  readonly tenantId: LaneId;
  readonly correlationId: string;
}

export interface InvocationAuth {
  readonly endpoint: string;
  readonly accessToken: AuthenticationArtifact;
  readonly binding: InvocationBinding;
}

export type StreamCallback = (event: StreamEvent) => void;

export type AgentInvocationErrorCode =
  | "session_required"
  | "session_expired"
  | "request_cancelled"
  | "request_failed";

const ERROR_MESSAGES: Readonly<Record<AgentInvocationErrorCode, string>> = {
  session_required: "Authentication is required.",
  session_expired: "The session has expired.",
  request_cancelled: "The request was cancelled.",
  request_failed: "The request failed.",
};

/** Stable, credential-free invocation failure bound to the captured session. */
export class AgentInvocationError extends Error {
  readonly code: AgentInvocationErrorCode;
  readonly binding: Readonly<InvocationBinding>;

  constructor(
    code: AgentInvocationErrorCode,
    binding: Readonly<InvocationBinding>
  ) {
    super(ERROR_MESSAGES[code]);
    this.name = "AgentInvocationError";
    this.code = code;
    this.binding = binding;
  }
}

function captureBinding(auth: InvocationAuth): Readonly<InvocationBinding> {
  const binding = Object.freeze({ ...auth.binding });
  const laneIsValid =
    binding.laneId === "Tenant_A" || binding.laneId === "Tenant_B";
  const tenantIsValid =
    binding.tenantId === "Tenant_A" || binding.tenantId === "Tenant_B";
  const requiredValues = [
    auth.endpoint,
    binding.sessionId,
    binding.subject,
    binding.correlationId,
  ];

  if (
    !isAuthenticationArtifact(auth.accessToken) ||
    auth.accessToken.provenance !== "access_token" ||
    !laneIsValid ||
    !tenantIsValid ||
    binding.laneId !== binding.tenantId ||
    !CORRELATION_ID_PATTERN.test(binding.correlationId) ||
    requiredValues.some((value) => typeof value !== "string" || !value.trim())
  ) {
    throw new AgentInvocationError("session_required", binding);
  }

  return binding;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function classifyFailure(
  payload: unknown,
  binding: Readonly<InvocationBinding>
): AgentInvocationErrorCode | null {
  if (!isRecord(payload) || typeof payload.code !== "string") {
    return null;
  }

  if (payload.correlation_id !== binding.correlationId) {
    return "request_failed";
  }

  return payload.code === "session_expired"
    ? "session_expired"
    : "request_failed";
}

function failureFromSSELine(
  line: string,
  binding: Readonly<InvocationBinding>
): AgentInvocationErrorCode | null {
  if (!line.startsWith("data: ")) return null;

  try {
    return classifyFailure(JSON.parse(line.slice(6).trim()), binding);
  } catch {
    return null;
  }
}

async function failureFromResponse(
  response: Response,
  binding: Readonly<InvocationBinding>
): Promise<AgentInvocationErrorCode> {
  try {
    return classifyFailure(await response.json(), binding) ?? "request_failed";
  } catch {
    return "request_failed";
  }
}

function isAbort(error: unknown, signal: AbortSignal): boolean {
  return signal.aborted || (error instanceof Error && error.name === "AbortError");
}

/** Send one query through only the endpoint and bearer captured for its session lane. */
export async function invokeAgent(
  query: string,
  auth: InvocationAuth,
  onEvent: StreamCallback,
  signal: AbortSignal
): Promise<void> {
  const binding = captureBinding(auth);

  try {
    signal.throwIfAborted();
    const response = await fetch(auth.endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: buildAuthorizationHeader(auth.accessToken),
        [CORRELATION_HEADER]: binding.correlationId,
      },
      body: JSON.stringify({ prompt: query }),
      signal,
    });

    if (!response.ok) {
      throw new AgentInvocationError(
        await failureFromResponse(response, binding),
        binding
      );
    }

    const parser: ChunkParser = (line, callback) => {
      const failure = failureFromSSELine(line, binding);
      if (failure) {
        throw new AgentInvocationError(failure, binding);
      }
      parseStrandsChunk(line, callback);
    };

    await readSSEStream(response, parser, (event) => {
      onEvent(event);
    });
  } catch (error) {
    if (error instanceof AgentInvocationError) throw error;
    throw new AgentInvocationError(
      isAbort(error, signal) ? "request_cancelled" : "request_failed",
      binding
    );
  }
}
