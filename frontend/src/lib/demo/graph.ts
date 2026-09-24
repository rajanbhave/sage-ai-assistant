/**
 * The demo stage set: the deployed Route C request path as a node/edge graph.
 *
 * `touchesForEvent` is the single mapping from a witnessed demo event to the
 * parts of the stage that light up. Every touch carries the evidence class of
 * what the browser can honestly claim, so the stage never animates a hop it did
 * not actually observe or correctly infer.
 */

export type EvidenceClass = "observed" | "inferred" | "configured";

export type NodeKind = "actor" | "identity" | "managed" | "application" | "data";

export interface GraphNode {
  readonly id: string;
  readonly label: string;
  readonly sublabel: string;
  readonly kind: NodeKind;
  /** Evidence available to the browser for this node. */
  readonly evidence: EvidenceClass;
  /** Layout position as a percentage of the stage box. */
  readonly x: number;
  readonly y: number;
}

export interface GraphEdge {
  readonly id: string;
  readonly from: string;
  readonly to: string;
  readonly label: string;
}

export const NODES: readonly GraphNode[] = Object.freeze([
  {
    id: "browser",
    label: "Browser",
    sublabel: "holds the only session",
    kind: "actor",
    evidence: "observed",
    x: 3,
    y: 40,
  },
  {
    id: "cognito",
    label: "Cognito",
    sublabel: "lane user pool",
    kind: "identity",
    evidence: "observed",
    x: 3,
    y: 6,
  },
  {
    id: "agent",
    label: "Agent Runtime",
    sublabel: "sage-agent/invoke",
    kind: "managed",
    evidence: "observed",
    x: 23,
    y: 40,
  },
  {
    id: "gateway",
    label: "Gateway",
    sublabel: "JWT_PASSTHROUGH",
    kind: "managed",
    evidence: "inferred",
    x: 42,
    y: 40,
  },
  {
    id: "mcp",
    label: "MCP Runtime",
    sublabel: "sage-mcp/invoke",
    kind: "managed",
    evidence: "inferred",
    x: 61,
    y: 40,
  },
  {
    id: "api",
    label: "Sage API",
    sublabel: "revalidates the JWT",
    kind: "application",
    evidence: "inferred",
    x: 80,
    y: 40,
  },
  {
    id: "data",
    label: "Tenant data",
    sublabel: "isolated by verified claim",
    kind: "data",
    evidence: "inferred",
    x: 80,
    y: 8,
  },
  {
    id: "other-lane",
    label: "Other lane",
    sublabel: "Agent Runtime",
    kind: "managed",
    evidence: "observed",
    x: 23,
    y: 76,
  },
]);

export const EDGES: readonly GraphEdge[] = Object.freeze([
  { id: "browser-cognito", from: "browser", to: "cognito", label: "authenticate" },
  { id: "browser-agent", from: "browser", to: "agent", label: "same bearer" },
  { id: "agent-gateway", from: "agent", to: "gateway", label: "same bearer" },
  { id: "gateway-mcp", from: "gateway", to: "mcp", label: "passthrough" },
  { id: "mcp-api", from: "mcp", to: "api", label: "same bearer" },
  { id: "api-data", from: "api", to: "data", label: "verified tenant" },
  { id: "browser-other-lane", from: "browser", to: "other-lane", label: "probe" },
]);

const NODE_IDS: ReadonlySet<string> = new Set(NODES.map((node) => node.id));

export type DemoEvent =
  /** A lane-bound session was established against that lane's Cognito pool. */
  | { readonly type: "session_established" }
  /** The run was submitted to the selected lane's Agent Runtime. */
  | { readonly type: "run_started" }
  /**
   * The Agent Runtime accepted the bearer and streamed its first event.
   *
   * The agent lists Gateway tools before streaming, so a first stream event also
   * proves the Gateway accepted the same bearer.
   */
  | { readonly type: "agent_accepted" }
  /** The model requested one MCP tool. */
  | { readonly type: "tool_started"; readonly name: string }
  /** A tool returned tenant data, so the Sage API validated and authorized it. */
  | { readonly type: "tool_completed"; readonly name: string }
  | { readonly type: "run_completed" }
  | { readonly type: "run_failed"; readonly code: string }
  /** The other lane's managed authorizer denied this lane's bearer. */
  | { readonly type: "cross_lane_rejected"; readonly status: number }
  /** The other lane did not deny the bearer, which is a failed expectation. */
  | { readonly type: "cross_lane_unexpected"; readonly status: number };

export interface Touch {
  readonly nodes: readonly string[];
  readonly edges: readonly string[];
  /** Marks a denial that must stay visible until the stage is reset. */
  readonly rejected?: boolean;
  /** Marks an expectation the demo failed to satisfy. */
  readonly failed?: boolean;
  /**
   * Marks a request the browser has sent but that nothing has yet accepted.
   *
   * Kept distinct from `active` so in-flight never reads as "this door accepted
   * the bearer". Only `agent_accepted` asserts acceptance.
   */
  readonly pending?: boolean;
}

const NOTHING: Touch = Object.freeze({ nodes: [], edges: [] });

/** Which nodes and edges one witnessed demo event lights up. */
export function touchesForEvent(event: DemoEvent): Touch {
  switch (event.type) {
    case "session_established":
      return { nodes: ["browser", "cognito"], edges: ["browser-cognito"] };

    case "run_started":
      // The browser has genuinely dispatched the request to this lane's Agent
      // Runtime, which is browser-observable, so the hop is shown in flight.
      // Acceptance is asserted only by `agent_accepted`.
      return {
        nodes: ["browser", "agent"],
        edges: ["browser-agent"],
        pending: true,
      };

    case "agent_accepted":
      // The agent lists Gateway tools before streaming, so a first stream event
      // proves the Gateway accepted this bearer. It does not prove the Gateway
      // forwarded the listing to the MCP Runtime, so `mcp` stays dark until a
      // tool actually round-trips.
      return {
        nodes: ["browser", "agent", "gateway"],
        edges: ["browser-agent", "agent-gateway"],
      };

    case "tool_started":
      return { nodes: ["gateway", "mcp"], edges: ["gateway-mcp"] };

    case "tool_completed":
      return { nodes: ["mcp", "api", "data"], edges: ["mcp-api", "api-data"] };

    case "run_completed":
      return NOTHING;

    case "run_failed":
      return { nodes: ["agent"], edges: ["browser-agent"], failed: true };

    case "cross_lane_rejected":
      return {
        nodes: ["other-lane"],
        edges: ["browser-other-lane"],
        rejected: true,
      };

    case "cross_lane_unexpected":
      return {
        nodes: ["other-lane"],
        edges: ["browser-other-lane"],
        failed: true,
      };
  }
}

/** True when every node referenced by the topology exists. */
export function graphIsConsistent(): boolean {
  return EDGES.every(
    (edge) => NODE_IDS.has(edge.from) && NODE_IDS.has(edge.to)
  );
}
