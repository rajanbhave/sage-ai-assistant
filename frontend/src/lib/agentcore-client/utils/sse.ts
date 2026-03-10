import type { ChunkParser, StreamCallback } from "../types";

/**
 * Reads a fetch Response body as a stream of SSE lines.
 * For each `data: ...` line, calls the parser with the raw line.
 * Handles chunked text decoding and line splitting.
 */
export async function readSSEStream(
  response: Response,
  parser: ChunkParser,
  callback: StreamCallback
): Promise<void> {
  if (!response.body) {
    throw new Error("Response body is null");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trimEnd();
        if (trimmed.startsWith("data: ")) {
          parser(trimmed, callback);
        }
      }
    }

    // Flush any remaining buffer content
    if (buffer.trim().startsWith("data: ")) {
      parser(buffer.trim(), callback);
    }
  } finally {
    reader.releaseLock();
  }
}
