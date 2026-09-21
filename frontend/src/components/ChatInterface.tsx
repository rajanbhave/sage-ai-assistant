import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ChatMessage } from "@/components/ChatMessage";
import {
  AgentInvocationError,
  createCorrelationId,
  invokeAgent,
  type InvocationBinding,
} from "@/lib/agentcore-client/client";
import {
  hasSameAuthenticationIdentity,
  renewSession,
  type AuthSession,
} from "@/lib/auth/cognito";
import {
  sanitizeUiText,
  type SafeMessageSegment,
  type SafeTextSegment,
  type SafeToolCallSegment,
} from "@/lib/safe-content";
import type { StreamEvent } from "@/lib/agentcore-client/types";

export type TextSegment = SafeTextSegment;
export type ToolCallSegment = SafeToolCallSegment;
export type MessageSegment = SafeMessageSegment;

export interface Message {
  id: string;
  role: "user" | "assistant";
  segments: MessageSegment[];
  isStreaming?: boolean;
}

interface ChatInterfaceProps {
  session: AuthSession;
  onSessionRenewed: (session: AuthSession) => void;
  onSessionTerminated: (session: AuthSession) => void;
}

interface ActiveInvocation {
  readonly binding: Readonly<InvocationBinding>;
  readonly controller: AbortController;
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/** Check all identity fields captured when an invocation was accepted. */
export function matchesInvocationBinding(
  session: AuthSession | null,
  binding: Readonly<InvocationBinding>
): boolean {
  return (
    session !== null &&
    session.sessionId === binding.sessionId &&
    session.lane.laneId === binding.laneId &&
    session.subject === binding.subject &&
    session.tenantId === binding.tenantId
  );
}

/** Apply one stream event only when it belongs to the current authenticated session. */
export function applyStreamEvent(
  messages: Message[],
  assistantId: string,
  event: StreamEvent,
  session: AuthSession | null,
  binding: Readonly<InvocationBinding>
): Message[] {
  if (!matchesInvocationBinding(session, binding)) return messages;

  const index = messages.findIndex((message) => message.id === assistantId);
  if (index === -1) return messages;

  const previous = messages[index]!;
  const message = {
    ...previous,
    segments: previous.segments,
  };

  switch (event.type) {
    case "text": {
      const content = sanitizeUiText(event.content);
      if (content === null) return messages;
      const last = message.segments[message.segments.length - 1];
      message.segments =
        last?.type === "text"
          ? [
              ...message.segments.slice(0, -1),
              { type: "text", content: last.content + content },
            ]
          : [...message.segments, { type: "text", content }];
      break;
    }
    case "tool_use_start": {
      const toolUseId = sanitizeUiText(event.toolUseId);
      const name = sanitizeUiText(event.name);
      if (toolUseId === null || name === null) return messages;
      message.segments = [
        ...message.segments,
        {
          type: "tool_call",
          toolUseId,
          name,
          input: "",
          status: "running",
        },
      ];
      break;
    }
    case "tool_use_delta": {
      const toolUseId = sanitizeUiText(event.toolUseId);
      const input = sanitizeUiText(event.input);
      if (toolUseId === null || input === null) return messages;
      message.segments = message.segments.map((segment) =>
        segment.type === "tool_call" && segment.toolUseId === toolUseId
          ? { ...segment, input: segment.input + input }
          : segment
      );
      break;
    }
    case "tool_result": {
      const toolUseId = sanitizeUiText(event.toolUseId);
      const result = sanitizeUiText(event.result);
      if (toolUseId === null) return messages;
      message.segments = message.segments.map((segment) =>
        segment.type === "tool_call" && segment.toolUseId === toolUseId
          ? {
              ...segment,
              ...(result === null ? {} : { result }),
              status: "complete" as const,
            }
          : segment
      );
      break;
    }
    case "result":
      message.isStreaming = false;
      break;
    case "message":
    case "lifecycle":
      return messages;
  }

  const updated = [...messages];
  updated[index] = message;
  return updated;
}

function replaceAssistantText(
  messages: Message[],
  assistantId: string,
  content: unknown
): Message[] {
  const index = messages.findIndex((message) => message.id === assistantId);
  if (index === -1) return messages;
  const updated = [...messages];
  updated[index] = {
    ...updated[index]!,
    segments: [
      { type: "text", content: sanitizeUiText(content) ?? "The request failed." },
    ],
    isStreaming: false,
  };
  return updated;
}

export function ChatInterface({
  session,
  onSessionRenewed,
  onSessionTerminated,
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isRenewing, setIsRenewing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sessionRef = useRef<AuthSession | null>(session);
  const activeInvocationRef = useRef<ActiveInvocation | null>(null);
  sessionRef.current = session;



  useEffect(() => {
    sessionRef.current = session;
    activeInvocationRef.current?.controller.abort();
    activeInvocationRef.current = null;
    setMessages([]);
    setInput("");
    setIsStreaming(false);
    setIsRenewing(false);

    return () => {
      sessionRef.current = null;
      activeInvocationRef.current?.controller.abort();
      activeInvocationRef.current = null;
    };
  }, [session.sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const terminateCurrentSession = useCallback(
    (current: AuthSession) => {
      if (sessionRef.current?.sessionId !== current.sessionId) return;
      sessionRef.current = null;
      activeInvocationRef.current?.controller.abort();
      activeInvocationRef.current = null;
      setMessages([]);
      setInput("");
      setIsStreaming(false);
      setIsRenewing(false);
      onSessionTerminated(current);
    },
    [onSessionTerminated]
  );

  const renewCurrentSession = useCallback(
    async (current: AuthSession): Promise<AuthSession | null> => {
      setIsRenewing(true);
      try {
        const renewed = await renewSession(current);
        if (
          sessionRef.current?.sessionId !== current.sessionId ||
          !hasSameAuthenticationIdentity(current, renewed)
        ) {
          return null;
        }
        sessionRef.current = renewed;
        onSessionRenewed(renewed);
        return renewed;
      } catch {
        terminateCurrentSession(current);
        return null;
      } finally {
        if (sessionRef.current?.sessionId === current.sessionId) {
          setIsRenewing(false);
        }
      }
    },
    [onSessionRenewed, terminateCurrentSession]
  );

  const handleSubmit = useCallback(async () => {
    const query = input.trim();
    if (!query || isStreaming || isRenewing) return;

    let invocationSession = sessionRef.current;
    if (!invocationSession) return;

    if (Date.now() >= invocationSession.expiresAt * 1000) {
      invocationSession = await renewCurrentSession(invocationSession);
      if (!invocationSession) return;
    }

    setInput("");
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      segments: [{ type: "text", content: query }],
    };
    const assistantId = generateId();
    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      segments: [],
      isStreaming: true,
    };
    setMessages((previous) => [
      ...previous,
      userMessage,
      assistantMessage,
    ]);
    setIsStreaming(true);

    const binding: InvocationBinding = Object.freeze({
      sessionId: invocationSession.sessionId,
      laneId: invocationSession.lane.laneId,
      subject: invocationSession.subject,
      tenantId: invocationSession.tenantId,
      correlationId: createCorrelationId(),
    });
    const controller = new AbortController();
    activeInvocationRef.current = { binding, controller };

    const updateBoundError = (content: string) => {
      setMessages((previous) =>
        matchesInvocationBinding(sessionRef.current, binding)
          ? replaceAssistantText(previous, assistantId, content)
          : previous
      );
    };

    try {
      await invokeAgent(
        query,
        {
          endpoint: invocationSession.lane.agentRuntimeEndpoint,
          accessToken: invocationSession.accessToken,
          binding,
        },
        (event) => {
          setMessages((previous) =>
            applyStreamEvent(
              previous,
              assistantId,
              event,
              sessionRef.current,
              binding
            )
          );
        },
        controller.signal
      );
    } catch (error) {
      const errorBinding =
        error instanceof AgentInvocationError ? error.binding : binding;
      if (!matchesInvocationBinding(sessionRef.current, errorBinding)) return;

      if (
        error instanceof AgentInvocationError &&
        error.code === "session_expired"
      ) {
        activeInvocationRef.current = null;
        updateBoundError("The session expired. Renewing before another attempt…");
        const renewed = await renewCurrentSession(invocationSession);
        if (renewed && matchesInvocationBinding(renewed, binding)) {
          setInput(query);
          updateBoundError(
            "Session renewed. Review the request and press Send to retry. Data-changing operations are never replayed automatically."
          );
        }
      } else if (
        error instanceof AgentInvocationError &&
        error.code === "request_cancelled"
      ) {
        updateBoundError("The request was cancelled.");
      } else {
        updateBoundError(
          error instanceof AgentInvocationError &&
            error.code === "session_required"
            ? "Authentication is required."
            : "The request failed."
        );
      }
    } finally {
      if (
        activeInvocationRef.current?.binding.correlationId ===
        binding.correlationId
      ) {
        activeInvocationRef.current = null;
      }
      if (matchesInvocationBinding(sessionRef.current, binding)) {
        setIsStreaming(false);
        setMessages((previous) =>
          previous.map((message) =>
            message.id === assistantId
              ? { ...message, isStreaming: false }
              : message
          )
        );
      }
    }
  }, [input, isRenewing, isStreaming, renewCurrentSession]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const isBusy = isStreaming || isRenewing;

  return (
    <div className="flex flex-col h-full">
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

      <div className="border-t border-border px-4 py-3 flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={1}
          disabled={isBusy}
          className="flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 max-h-40 overflow-y-auto"
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        <Button
          onClick={handleSubmit}
          disabled={!input.trim() || isBusy}
          size="default"
        >
          {isRenewing ? "Renewing…" : isStreaming ? "…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
