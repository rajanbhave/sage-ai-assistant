import type { ChunkParser, StreamCallback } from "../types";

/**
 * Parses Strands SSE events into typed StreamEvents.
 *
 * Strands emits the following event shapes:
 * - Text token:       {"data": "Hello"}
 * - Tool use start:   {"current_tool_use": {"toolUseId": "...", "name": "..."}, "delta": {"toolUse": {"input": ""}}}
 * - Tool use delta:   {"current_tool_use": {...}, "delta": {"toolUse": {"input": "..."}}}
 * - Tool result:      {"message": {"role": "user", "content": [{"toolResult": {"toolUseId": "...", "content": [{"text": "..."}]}}]}}
 * - Final result:     {"result": {"stop_reason": "end_turn"}}
 * - Lifecycle:        {"event": "init_event_loop"}
 */
export const parseStrandsChunk: ChunkParser = (line: string, callback: StreamCallback): void => {
  if (!line.startsWith("data: ")) return;

  const raw = line.substring(6).trim();
  if (!raw) return;

  let json: Record<string, unknown>;
  try {
    json = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    // Ignore malformed JSON lines
    return;
  }

  // Text token: {"data": "Hello"}
  if (typeof json.data === "string") {
    callback({ type: "text", content: json.data });
    return;
  }

  // Tool use start / delta: {"current_tool_use": {...}, "delta": {"toolUse": {...}}}
  if (json.current_tool_use && typeof json.current_tool_use === "object") {
    const tool = json.current_tool_use as Record<string, unknown>;
    const toolUseId = typeof tool.toolUseId === "string" ? tool.toolUseId : "";
    const name = typeof tool.name === "string" ? tool.name : "";

    const delta = json.delta as Record<string, unknown> | undefined;
    const toolUseDelta = delta?.toolUse as Record<string, unknown> | undefined;
    const input = toolUseDelta?.input;

    if (input === "") {
      // Empty input string signals the start of a tool use
      callback({ type: "tool_use_start", toolUseId, name });
    } else if (typeof input === "string" && input.length > 0) {
      callback({ type: "tool_use_delta", toolUseId, input });
    }
    return;
  }

  // Tool result from user message:
  // {"message": {"role": "user", "content": [{"toolResult": {"toolUseId": "...", "content": [{"text": "..."}]}}]}}
  if (json.message && typeof json.message === "object") {
    const message = json.message as Record<string, unknown>;
    if (message.role === "user" && Array.isArray(message.content)) {
      for (const block of message.content as unknown[]) {
        if (block && typeof block === "object") {
          const b = block as Record<string, unknown>;
          if (b.toolResult && typeof b.toolResult === "object") {
            const toolResult = b.toolResult as Record<string, unknown>;
            const toolUseId = typeof toolResult.toolUseId === "string" ? toolResult.toolUseId : "";
            let result = "";
            if (Array.isArray(toolResult.content)) {
              const textBlocks = (toolResult.content as unknown[])
                .filter((c): c is Record<string, unknown> => typeof c === "object" && c !== null)
                .map((c) => (typeof c.text === "string" ? c.text : ""))
                .join("");
              result = textBlocks;
            }
            callback({ type: "tool_result", toolUseId, result });
          }
        }
      }
      // Also emit the full message event
      callback({ type: "message", role: String(message.role), content: message.content as unknown[] });
      return;
    }
  }

  // Final result: {"result": {"stop_reason": "end_turn"}}
  if (json.result && typeof json.result === "object") {
    const result = json.result as Record<string, unknown>;
    const stopReason = typeof result.stop_reason === "string" ? result.stop_reason : "end_turn";
    callback({ type: "result", stopReason });
    return;
  }

  // Lifecycle event: {"event": "init_event_loop"}
  if (typeof json.event === "string") {
    callback({ type: "lifecycle", event: json.event });
    return;
  }
};
