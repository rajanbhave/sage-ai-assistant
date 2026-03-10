import { cn } from "@/lib/utils";

// --- Types (aligned with ChatInterface segment model) ---

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

export interface ChatMessageProps {
  role: "user" | "assistant";
  segments: MessageSegment[];
  isStreaming?: boolean;
}

// --- Minimal markdown renderer ---
// Handles: **bold**, *italic*, `inline code`, ```code blocks```, and - list items.

function renderMarkdown(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];

  // Split on fenced code blocks first
  const codeBlockRegex = /```[\w]*\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(text)) !== null) {
    // Render text before the code block
    if (match.index > lastIndex) {
      nodes.push(...renderInlineMarkdown(text.slice(lastIndex, match.index)));
    }
    // Render the code block
    nodes.push(
      <pre
        key={`code-${match.index}`}
        className="my-2 rounded-md bg-muted/80 px-3 py-2 text-xs font-mono overflow-x-auto whitespace-pre"
      >
        <code>{(match[1] ?? "").trimEnd()}</code>
      </pre>
    );
    lastIndex = match.index + match[0].length;
  }

  // Render remaining text
  if (lastIndex < text.length) {
    nodes.push(...renderInlineMarkdown(text.slice(lastIndex)));
  }

  return nodes;
}

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  return lines.map((line, lineIdx) => {
    const isListItem = /^[-*]\s/.test(line);
    const content = isListItem ? line.slice(2) : line;
    const inlineNodes = renderInlineTokens(content);

    if (isListItem) {
      return (
        <li key={lineIdx} className="ml-4 list-disc">
          {inlineNodes}
        </li>
      );
    }

    // Empty line → paragraph break
    if (line.trim() === "") {
      return <br key={lineIdx} />;
    }

    return (
      <span key={lineIdx}>
        {inlineNodes}
        {lineIdx < lines.length - 1 && "\n"}
      </span>
    );
  });
}

function renderInlineTokens(text: string): React.ReactNode[] {
  // Pattern: **bold**, *italic*, `code`
  const tokenRegex = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = tokenRegex.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(text.slice(last, m.index));
    }
    if (m[2] !== undefined) {
      nodes.push(<strong key={m.index}>{m[2]}</strong>);
    } else if (m[3] !== undefined) {
      nodes.push(<em key={m.index}>{m[3]}</em>);
    } else if (m[4] !== undefined) {
      nodes.push(
        <code
          key={m.index}
          className="rounded bg-muted/80 px-1 py-0.5 text-xs font-mono"
        >
          {m[4]}
        </code>
      );
    }
    last = m.index + m[0].length;
  }

  if (last < text.length) {
    nodes.push(text.slice(last));
  }

  return nodes;
}

// --- ToolActivity sub-component ---

function ToolActivity({ seg }: { seg: ToolCallSegment }) {
  return (
    <div className="my-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs font-mono">
      <div className="flex items-center gap-2 mb-1">
        <span
          className={cn(
            "inline-block size-2 rounded-full",
            seg.status === "running"
              ? "bg-yellow-400 animate-pulse"
              : "bg-green-500"
          )}
        />
        <span className="font-semibold text-foreground">{seg.name}</span>
        <span className="text-muted-foreground">
          {seg.status === "running" ? "running…" : "complete"}
        </span>
      </div>

      {seg.input && (
        <div className="text-muted-foreground truncate">
          <span className="text-foreground/60">input: </span>
          {seg.input}
        </div>
      )}

      {seg.result && (
        <div className="mt-1 text-muted-foreground line-clamp-3">
          <span className="text-foreground/60">result: </span>
          {seg.result}
        </div>
      )}
    </div>
  );
}

// --- ChatMessage component ---

export function ChatMessage({ role, segments, isStreaming }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-xl px-4 py-3 text-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        )}
      >
        {segments.map((seg, i) => {
          if (seg.type === "text") {
            if (isUser) {
              // User messages: plain whitespace-preserved text
              return (
                <p key={i} className="whitespace-pre-wrap">
                  {seg.content}
                </p>
              );
            }
            // Assistant messages: markdown rendering
            return (
              <div key={i} className="whitespace-pre-wrap leading-relaxed">
                {renderMarkdown(seg.content)}
              </div>
            );
          }

          // Tool call segment
          return <ToolActivity key={seg.toolUseId} seg={seg} />;
        })}

        {/* Streaming dots when no content yet */}
        {isStreaming && segments.length === 0 && (
          <span className="inline-flex gap-1">
            <span className="animate-bounce [animation-delay:0ms]">·</span>
            <span className="animate-bounce [animation-delay:150ms]">·</span>
            <span className="animate-bounce [animation-delay:300ms]">·</span>
          </span>
        )}
      </div>
    </div>
  );
}
