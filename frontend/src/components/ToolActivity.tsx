import { cn } from "@/lib/utils";

export interface ToolActivityProps {
  toolUseId: string;
  name: string;
  status: "running" | "complete";
  inputDelta?: string;
  result?: string;
}

export function ToolActivity({ name, status, inputDelta, result }: ToolActivityProps) {
  return (
    <div className="my-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs font-mono">
      <div className="flex items-center gap-2 mb-1">
        {status === "running" ? (
          <span className="inline-block size-2 rounded-full bg-yellow-400 animate-pulse" />
        ) : (
          <span className="inline-block size-2 rounded-full bg-green-500" />
        )}
        <code className={cn("font-semibold text-foreground")}>{name}</code>
        <span className="text-muted-foreground">
          {status === "running" ? "running…" : "complete"}
        </span>
      </div>

      {inputDelta && (
        <div className="text-muted-foreground truncate">
          <span className="text-foreground/60">input: </span>
          {inputDelta}
        </div>
      )}

      {result && (
        <div className="mt-1 text-muted-foreground">
          <span className="text-foreground/60">result: </span>
          <span className="line-clamp-2">
            {result.length > 100 ? `${result.slice(0, 100)}…` : result}
          </span>
        </div>
      )}
    </div>
  );
}
