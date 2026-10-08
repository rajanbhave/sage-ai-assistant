import { EDGES, NODES, type GraphNode } from "@/lib/demo/graph";
import type { VisualStatus } from "@/lib/demo/stage-state";
import { cn } from "@/lib/utils";

/**
 * The stage set: node cards over an SVG edge layer sharing one percent
 * coordinate system. Pure view — all state comes from the stage reducer.
 */

interface DemoStageProps {
  nodeStates: Readonly<Record<string, VisualStatus>>;
  edgeStates: Readonly<Record<string, VisualStatus>>;
  laneLabel: string;
  otherLaneLabel: string;
}

const CARD_W = 17;
const CARD_H = 16;

const NODE_STATUS_CLASS: Record<VisualStatus, string> = {
  idle: "border-border bg-card/40 text-muted-foreground",
  pending:
    "border-primary/50 bg-card/70 text-foreground [border-style:dashed] animate-pulse",
  active: "border-primary bg-card text-foreground shadow-lg ring-2 ring-primary/40",
  done: "border-primary/40 bg-card text-foreground",
  rejected: "border-destructive bg-destructive/10 text-foreground ring-2 ring-destructive/40",
  failed: "border-destructive/60 bg-destructive/5 text-foreground",
};

const EDGE_STATUS_CLASS: Record<VisualStatus, string> = {
  idle: "stroke-border",
  pending: "stroke-primary/60 [stroke-dasharray:3_2]",
  active: "stroke-primary",
  done: "stroke-primary/40",
  rejected: "stroke-destructive",
  failed: "stroke-destructive/60",
};

const EVIDENCE_LABEL = {
  observed: "observed",
  inferred: "inferred",
  configured: "config",
} as const;

const NODE_STATUS_TEXT: Record<VisualStatus, string> = {
  idle: "idle",
  pending: "in flight",
  active: "active",
  done: "passed",
  rejected: "denied",
  failed: "failed",
};

function center(node: GraphNode): { cx: number; cy: number } {
  return { cx: node.x + CARD_W / 2, cy: node.y + CARD_H / 2 };
}

function nodeById(id: string): GraphNode | undefined {
  return NODES.find((node) => node.id === id);
}

/** Orthogonal elbow path between two card centres. */
function edgePath(fromId: string, toId: string): string {
  const from = nodeById(fromId);
  const to = nodeById(toId);
  if (!from || !to) return "";
  const a = center(from);
  const b = center(to);
  if (Math.abs(a.cx - b.cx) < 1 || Math.abs(a.cy - b.cy) < 1) {
    return `M ${a.cx} ${a.cy} L ${b.cx} ${b.cy}`;
  }
  const midY = (a.cy + b.cy) / 2;
  return `M ${a.cx} ${a.cy} L ${a.cx} ${midY} L ${b.cx} ${midY} L ${b.cx} ${b.cy}`;
}

/** Clearance above a card row for a same-row edge label, in viewBox percent. */
const LABEL_CLEARANCE = 3.5;

function edgeLabelPos(fromId: string, toId: string): { x: number; y: number } {
  const from = nodeById(fromId);
  const to = nodeById(toId);
  if (!from || !to) return { x: 0, y: 0 };
  const a = center(from);
  const b = center(to);
  if (Math.abs(a.cy - b.cy) < 1) {
    // Cards in the same row sit 2–3% apart, far narrower than a label like
    // "same bearer", so a midpoint label would be overlapped by the card layer
    // that paints after it. Lift it clear of the row instead.
    return {
      x: (a.cx + b.cx) / 2,
      y: Math.min(from.y, to.y) - LABEL_CLEARANCE,
    };
  }
  return { x: (a.cx + b.cx) / 2, y: (a.cy + b.cy) / 2 };
}

export function DemoStage({
  nodeStates,
  edgeStates,
  laneLabel,
  otherLaneLabel,
}: DemoStageProps) {
  return (
    <div
      className="relative w-full h-full min-h-[22rem]"
      data-testid="demo-stage"
    >
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden
      >
        {EDGES.map((edge) => {
          const status = edgeStates[edge.id] ?? "idle";
          return (
            <path
              key={edge.id}
              data-edge={edge.id}
              data-status={status}
              className={cn(
                "fill-none transition-colors duration-300",
                EDGE_STATUS_CLASS[status],
                edge.id === "browser-other-lane" && status === "idle"
                  ? "[stroke-dasharray:2_2]"
                  : ""
              )}
              strokeWidth={status === "active" ? 2 : 1}
              d={edgePath(edge.from, edge.to)}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      <div className="absolute inset-0" aria-hidden>
        {EDGES.map((edge) => {
          const pos = edgeLabelPos(edge.from, edge.to);
          const status = edgeStates[edge.id] ?? "idle";
          return (
            <span
              key={`label-${edge.id}`}
              className={cn(
                "absolute -translate-x-1/2 -translate-y-1/2 rounded bg-background/90 px-1 font-mono text-[10px] transition-colors",
                status === "idle" ? "text-muted-foreground" : "text-foreground"
              )}
              style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
            >
              {edge.label}
            </span>
          );
        })}
      </div>

      {NODES.map((node) => {
        const status = nodeStates[node.id] ?? "idle";
        const sublabel =
          node.id === "other-lane"
            ? `${otherLaneLabel} — must deny`
            : node.id === "cognito" || node.id === "data"
              ? `${laneLabel} · ${node.sublabel}`
              : node.sublabel;
        return (
          <div
            key={node.id}
            data-testid={`stage-node-${node.id}`}
            data-status={status}
            role="status"
            aria-label={`${node.label}: ${NODE_STATUS_TEXT[status]}`}
            className={cn(
              "absolute flex flex-col justify-center rounded-lg border px-2 py-1.5 transition-all duration-300",
              NODE_STATUS_CLASS[status]
            )}
            style={{
              left: `${node.x}%`,
              top: `${node.y}%`,
              width: `${CARD_W}%`,
              height: `${CARD_H}%`,
            }}
          >
            {/*
              `shrink-0` is required: these are flex children of a fixed-height
              card, so without it they shrink below their line height and
              `truncate`'s overflow:hidden clips the descenders — "Cognito"
              renders as "Coanito".
            */}
            <span className="shrink-0 truncate text-xs font-semibold leading-normal">
              {node.label}
            </span>
            <span className="shrink-0 truncate font-mono text-[10px] leading-normal text-muted-foreground">
              {sublabel}
            </span>
            <span className="mt-0.5 flex shrink-0 items-center justify-between gap-1 font-mono text-[9px] uppercase leading-normal tracking-wide text-muted-foreground/80">
              <span>{EVIDENCE_LABEL[node.evidence]}</span>
              {/* Status is also stated in text so it is not conveyed by colour alone. */}
              {status !== "idle" && (
                <span
                  className={
                    status === "rejected" || status === "failed"
                      ? "text-destructive"
                      : "text-foreground"
                  }
                >
                  {NODE_STATUS_TEXT[status]}
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
