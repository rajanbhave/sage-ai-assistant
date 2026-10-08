import { touchesForEvent, type DemoEvent } from "./graph";

/**
 * Event-driven stage state.
 *
 * A pure reducer: witnessed demo events in, node and edge visual states out.
 * Each event demotes the previously active parts to `done`, which reads as one
 * request moving through the deployed path. A denial is sticky so a cross-lane
 * rejection stays on screen until the presenter resets the stage.
 */

export type VisualStatus =
  | "idle"
  | "pending"
  | "active"
  | "done"
  | "rejected"
  | "failed";

export interface StageState {
  readonly nodeStates: Readonly<Record<string, VisualStatus>>;
  readonly edgeStates: Readonly<Record<string, VisualStatus>>;
  readonly running: boolean;
  readonly rejected: boolean;
  readonly failure?: string;
}

export type StageAction =
  | { readonly kind: "start" }
  | { readonly kind: "event"; readonly event: DemoEvent }
  | { readonly kind: "reset" };

export const initialStageState: StageState = Object.freeze({
  nodeStates: {},
  edgeStates: {},
  running: false,
  rejected: false,
});

const STICKY: ReadonlySet<VisualStatus> = new Set<VisualStatus>([
  "rejected",
  "failed",
]);

function demoteActive(
  states: Readonly<Record<string, VisualStatus>>
): Record<string, VisualStatus> {
  const next: Record<string, VisualStatus> = {};
  for (const [id, status] of Object.entries(states)) {
    next[id] = status === "active" ? "done" : status;
  }
  return next;
}

function settlePending(
  states: Readonly<Record<string, VisualStatus>>
): Record<string, VisualStatus> {
  const next: Record<string, VisualStatus> = {};
  for (const [id, status] of Object.entries(states)) {
    // Anything still in flight when the run ends was never proven, so it goes
    // back to idle rather than being promoted as if it had succeeded.
    next[id] = status === "pending" ? "idle" : status;
  }
  return next;
}

function applyTouch(
  state: StageState,
  event: DemoEvent
): StageState {
  const touch = touchesForEvent(event);
  const nodeStates = demoteActive(state.nodeStates);
  const edgeStates = demoteActive(state.edgeStates);
  const status: VisualStatus = touch.rejected
    ? "rejected"
    : touch.failed
      ? "failed"
      : touch.pending
        ? "pending"
        : "active";

  for (const id of touch.nodes) {
    if (!STICKY.has(nodeStates[id] as VisualStatus)) nodeStates[id] = status;
  }
  for (const id of touch.edges) {
    if (!STICKY.has(edgeStates[id] as VisualStatus)) edgeStates[id] = status;
  }

  return {
    ...state,
    nodeStates,
    edgeStates,
    rejected: state.rejected || touch.rejected === true,
  };
}

export function stageReducer(state: StageState, action: StageAction): StageState {
  switch (action.kind) {
    case "reset":
      return initialStageState;

    case "start":
      return {
        nodeStates: demoteActive(state.nodeStates),
        edgeStates: demoteActive(state.edgeStates),
        running: true,
        rejected: state.rejected,
      };

    case "event": {
      const event = action.event;

      if (event.type === "run_completed") {
        return {
          ...state,
          nodeStates: settlePending(demoteActive(state.nodeStates)),
          edgeStates: settlePending(demoteActive(state.edgeStates)),
          running: false,
        };
      }

      if (event.type === "run_failed") {
        const touched = applyTouch(state, event);
        return {
          ...touched,
          nodeStates: settlePending(touched.nodeStates),
          edgeStates: settlePending(touched.edgeStates),
          running: false,
          failure: event.code,
        };
      }

      return applyTouch(state, event);
    }
  }
}
