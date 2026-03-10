import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ChatMessage } from "@/components/ChatMessage";
import { invokeAgent } from "@/lib/agentcore-client/client";
import type { StreamEvent } from "@/lib/agentcore-client/types";

// --- Segment model ---

interface TextSegment {
  type: "text";
  content: string;
}

interface ToolCallSegment {
  type: "tool_call";
  toolUseId: string;
  name: string;
  input: string;
  result?: string;
  status: "running" | "complete";
}

type MessageSegment = TextSegment | ToolCallSegment;

interface Message {
  id: string;
  role: "user" | "assistant";
  segments: MessageSegment[];
  isStreaming?: boolean;
}

// --- Props ---

interface ChatInterfaceProps {
  tenantId: string;
}

// --- Helpers ---

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

// --- Component ---

export function ChatInterface({ tenantId }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Clear messages when tenant changes
  useEffect(() => {
    setMessages([]);
    setInput("");
    setIsStreaming(false);
  }, [tenantId]);

  // Auto-scroll to bottom whenever messages update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = useCallback(async () => {
    const query = input.trim();
    if (!query || isStreaming) return;

    setInput("");

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      segments: [{ type: "text", content: query }],
    };

    // Placeholder for the assistant response being built
    const assistantId = generateId();
    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      segments: [],
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setIsStreaming(true);

    try {
      await invokeAgent(query, tenantId, (event: StreamEvent) => {
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === assistantId);
          if (idx === -1) return prev;

          const prevMsg = prev[idx]!;
          const msg = { ...prevMsg, segments: [...prevMsg.segments] };

          switch (event.type) {
            case "text": {
              // Append to last text segment or create a new one
              const last = msg.segments[msg.segments.length - 1];
              if (last?.type === "text") {
                msg.segments = [
                  ...msg.segments.slice(0, -1),
                  { type: "text", content: last.content + event.content },
                ];
              } else {
                msg.segments = [
                  ...msg.segments,
                  { type: "text", content: event.content },
                ];
              }
              break;
            }

            case "tool_use_start": {
              msg.segments = [
                ...msg.segments,
                {
                  type: "tool_call",
                  toolUseId: event.toolUseId,
                  name: event.name,
                  input: "",
                  status: "running",
                },
              ];
              break;
            }

            case "tool_use_delta": {
              msg.segments = msg.segments.map((seg) =>
                seg.type === "tool_call" && seg.toolUseId === event.toolUseId
                  ? { ...seg, input: seg.input + event.input }
                  : seg
              );
              break;
            }

            case "tool_result": {
              msg.segments = msg.segments.map((seg) =>
                seg.type === "tool_call" && seg.toolUseId === event.toolUseId
                  ? { ...seg, result: event.result, status: "complete" as const }
                  : seg
              );
              break;
            }

            case "result": {
              msg.isStreaming = false;
              break;
            }

            default:
              break;
          }

          const updated = [...prev];
          updated[idx] = msg as Message;
          return updated;
        });
      });
    } catch (err) {
      const errorText =
        err instanceof Error ? err.message : "An unexpected error occurred.";
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === assistantId);
        if (idx === -1) return prev;
        const updated = [...prev];
        updated[idx] = {
          ...updated[idx]!,
          segments: [{ type: "text", content: `Error: ${errorText}` }],
          isStreaming: false,
        } as Message;
        return updated;
      });
    } finally {
      setIsStreaming(false);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, isStreaming: false } : m
        )
      );
    }
  }, [input, isStreaming, tenantId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-center text-muted-foreground text-sm mt-8">
            Ask Sage anything about your insurance policies or claims.
          </p>
        )}

        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            role={message.role}
            segments={message.segments}
            isStreaming={message.isStreaming}
          />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-border px-4 py-3 flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={1}
          disabled={isStreaming}
          className="flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 max-h-40 overflow-y-auto"
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        <Button
          onClick={handleSubmit}
          disabled={!input.trim() || isStreaming}
          size="default"
        >
          {isStreaming ? "…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
