import { isAuthenticationArtifact } from "@/lib/auth/artifact";

export interface SafeTextSegment {
  readonly type: "text";
  readonly content: string;
}

export interface SafeToolCallSegment {
  readonly type: "tool_call";
  readonly toolUseId: string;
  readonly name: string;
  readonly input: string;
  readonly result?: string;
  readonly status: "running" | "complete";
}

export type SafeMessageSegment = SafeTextSegment | SafeToolCallSegment;

/** Admit only an unclassified string into a UI text field. */
export function sanitizeUiText(value: unknown): string | null {
  if (isAuthenticationArtifact(value)) return null;
  return typeof value === "string" ? value : null;
}
