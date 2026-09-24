import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { DemoStage } from "@/components/DemoStage";
import {
  AgentInvocationError,
  createCorrelationId,
  invokeAgent,
  type InvocationBinding,
} from "@/lib/agentcore-client/client";
import type { StreamEvent } from "@/lib/agentcore-client/types";
import { TENANT_DISPLAY_NAMES, type AuthSession, type LaneId } from "@/lib/auth/cognito";
import { buildLogsInsightsUrl } from "@/lib/demo/config";
import { probeOtherLane } from "@/lib/demo/cross-lane-probe";
import type { DemoEvent } from "@/lib/demo/graph";
import { promptPresets } from "@/lib/demo/presets";
import { initialStageState, stageReducer } from "@/lib/demo/stage-state";
import { sanitizeUiText } from "@/lib/safe-content";

/**
 * The JWT-passthrough demo stage, wired to the real deployed path.
 *
 * Every animation and feed line is produced by something this browser actually
 * witnessed: the Cognito result, the Agent Runtime response status, the streamed
 * Strands events, and the other lane's denial status. Nothing is choreographed.
 */

interface DemoStageAppProps {
  session: AuthSession;
}

interface FeedItem {
  readonly id: string;
  readonly time: string;
  readonly level: "INFO" | "DENIED" | "ERROR";
  readonly text: string;
  readonly href?: string;
}

function otherLaneId(laneId: LaneId): LaneId {
  return laneId === "Tenant_A" ? "Tenant_B" : "Tenant_A";
}

function clockTime(): string {
  return new Date().toISOString().slice(11, 19);
}

/** Map one streamed agent event onto the demo events it proves. */
function demoEventsFor(event: StreamEvent): readonly DemoEvent[] {
  switch (event.type) {
    case "tool_use_start":
      return [{ type: "tool_started", name: event.name }];
    case "tool_result":
      return [{ type: "tool_completed", name: event.toolUseId }];
    case "result":
      return [{ type: "run_completed" }];
    default:
      return [];
  }
}

export function DemoStageApp({ session }: DemoStageAppProps) {
  const [stage, dispatch] = useReducer(stageReducer, initialStageState);
  const [answer, setAnswer] = useState("");
  const [feed, setFeed] = useState<readonly FeedItem[]>([]);
  const [busy, setBusy] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const presets = promptPresets(session.lane.laneId);
  const laneLabel = TENANT_DISPLAY_NAMES[session.tenantId];
  const otherLabel = TENANT_DISPLAY_NAMES[otherLaneId(session.lane.laneId)];

  const addFeed = useCallback(
    (level: FeedItem["level"], text: string, href?: string) => {
      setFeed((previous) => [
        ...previous,
        {
          id: `${Date.now()}-${previous.length}`,
          time: clockTime(),
          level,
          text,
          ...(href ? { href } : {}),
        },
      ]);
    },
    []
  );

  useEffect(() => {
    dispatch({ kind: "reset" });
    dispatch({ kind: "event", event: { type: "session_established" } });
    setAnswer("");
    setFeed([
      {
        id: "session",
        time: clockTime(),
        level: "INFO",
        text: `session established in ${session.lane.laneId} against its own Cognito pool`,
      },
    ]);
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [session.sessionId, session.lane.laneId]);

  const run = useCallback(
    async (prompt: string) => {
      if (busy) return;
      setBusy(true);
      setAnswer("");
      dispatch({ kind: "start" });

      const binding: InvocationBinding = Object.freeze({
        sessionId: session.sessionId,
        laneId: session.lane.laneId,
        subject: session.subject,
        tenantId: session.tenantId,
        correlationId: createCorrelationId(),
      });
      const controller = new AbortController();
      controllerRef.current = controller;
      let accepted = false;

      const logsUrl = buildLogsInsightsUrl(
        session.lane.laneId,
        binding.correlationId
      );
      dispatch({ kind: "event", event: { type: "run_started" } });
      addFeed(
        "INFO",
        `run ${binding.correlationId} submitted to the ${session.lane.laneId} Agent Runtime`,
        logsUrl ?? undefined
      );

      try {
        await invokeAgent(
          prompt,
          {
            endpoint: session.lane.agentRuntimeEndpoint,
            accessToken: session.accessToken,
            binding,
          },
          (event) => {
            if (!accepted) {
              accepted = true;
              dispatch({ kind: "event", event: { type: "agent_accepted" } });
              addFeed(
                "INFO",
                "Agent Runtime accepted the bearer; Gateway tool listing succeeded, so the Gateway accepted the same bearer"
              );
            }
            if (event.type === "text") {
              const content = sanitizeUiText(event.content);
              if (content !== null) setAnswer((prev) => prev + content);
            }
            if (event.type === "tool_use_start") {
              addFeed("INFO", `tool ${event.name} requested`);
            }
            if (event.type === "tool_result") {
              addFeed(
                "INFO",
                "tool returned tenant data, so the Sage API independently validated the same bearer and authorized this tenant"
              );
            }
            for (const demoEvent of demoEventsFor(event)) {
              dispatch({ kind: "event", event: demoEvent });
            }
          },
          controller.signal
        );
      } catch (error) {
        const code =
          error instanceof AgentInvocationError ? error.code : "request_failed";
        dispatch({ kind: "event", event: { type: "run_failed", code } });
        addFeed("ERROR", `run failed: ${code}`);
      } finally {
        dispatch({ kind: "event", event: { type: "run_completed" } });
        if (controllerRef.current === controller) controllerRef.current = null;
        setBusy(false);
      }
    },
    [addFeed, busy, session]
  );

  const probe = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      const result = await probeOtherLane(session, controller.signal);
      const logsUrl = buildLogsInsightsUrl(
        result.targetLaneId,
        result.correlationId
      );
      if (result.denied && result.status !== null) {
        dispatch({
          kind: "event",
          event: { type: "cross_lane_rejected", status: result.status },
        });
        addFeed(
          "DENIED",
          `${result.targetLaneId} Agent Runtime denied this lane's bearer with HTTP ${result.status}`,
          logsUrl ?? undefined
        );
      } else {
        dispatch({
          kind: "event",
          event: { type: "cross_lane_unexpected", status: result.status ?? 0 },
        });
        addFeed(
          "ERROR",
          result.status === null
            ? `probe to ${result.targetLaneId} could not complete; no denial was observed`
            : `${result.targetLaneId} returned HTTP ${result.status} instead of denying the bearer`
        );
      }
    } catch {
      addFeed("ERROR", "the cross-lane probe is disabled in this build");
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      setBusy(false);
    }
  }, [addFeed, busy, session]);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    dispatch({ kind: "reset" });
    dispatch({ kind: "event", event: { type: "session_established" } });
    setAnswer("");
    setFeed([]);
    setBusy(false);
  }, []);

  const claims = session.claims;
  const status = stage.rejected
    ? "● Cross-lane bearer denied"
    : busy
      ? "● Executing"
      : feed.length > 1
        ? "● Run complete"
        : "● Standby";

  return (
    <div className="flex flex-col gap-3 h-full overflow-y-auto">
      <div className="relative rounded-xl border border-border bg-background/60 p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Route C request path — {laneLabel}
          </span>
          <span
            className="font-mono text-[11px] text-muted-foreground"
            data-testid="stage-status"
          >
            {status}
          </span>
        </div>
        <DemoStage
          nodeStates={stage.nodeStates}
          edgeStates={stage.edgeStates}
          laneLabel={laneLabel}
          otherLaneLabel={otherLabel}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-border p-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Validated claims — one bearer for the whole path
          </span>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-[11px]">
            <dt className="text-muted-foreground">jti</dt>
            <dd className="truncate">{claims.tokenId || "not present"}</dd>
            <dt className="text-muted-foreground">iss</dt>
            <dd className="truncate">{claims.issuer}</dd>
            <dt className="text-muted-foreground">client_id</dt>
            <dd className="truncate">{claims.clientId}</dd>
            <dt className="text-muted-foreground">token_use</dt>
            <dd>{claims.tokenUse}</dd>
            <dt className="text-muted-foreground">tenant</dt>
            <dd>{claims.tenantId}</dd>
            <dt className="text-muted-foreground">sub</dt>
            <dd className="truncate">{claims.subject}</dd>
            <dt className="text-muted-foreground">scope</dt>
            <dd className="break-words">
              {claims.scopes.length > 0 ? claims.scopes.join(" ") : "none"}
            </dd>
            <dt className="text-muted-foreground">exp</dt>
            <dd>{new Date(claims.expiresAt * 1000).toISOString()}</dd>
          </dl>
          <p className="mt-2 text-[11px] text-muted-foreground">
            The bearer itself is never displayed. <span className="font-mono">jti</span>{" "}
            identifies the token without being usable as one.
          </p>
        </div>

        <div className="rounded-xl border border-border p-3 flex flex-col">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Answer
          </span>
          <div className="mt-2 flex-1 whitespace-pre-wrap text-sm">
            {answer || (
              <span className="text-muted-foreground">
                Run a preset to stream a real answer through the deployed path.
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {presets.map((preset) => (
          <Button
            key={preset.key}
            variant="outline"
            size="sm"
            disabled={busy}
            title={preset.note}
            onClick={() => run(preset.prompt)}
          >
            {preset.label}
          </Button>
        ))}
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          title={`Send this lane's bearer to the ${otherLabel} Agent Runtime and show the managed denial.`}
          onClick={probe}
        >
          Cross-lane probe
        </Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={reset}>
          Reset
        </Button>
      </div>

      <div className="rounded-xl border border-border p-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Witnessed evidence
        </span>
        <div
          className="mt-2 space-y-1 font-mono text-[11px]"
          data-testid="evidence-feed"
        >
          {feed.length === 0 ? (
            <span className="text-muted-foreground">Standby.</span>
          ) : (
            feed.map((item) => (
              <div key={item.id} className="flex gap-2">
                <span className="text-muted-foreground">{item.time}</span>
                <span
                  className={
                    item.level === "INFO"
                      ? "text-muted-foreground"
                      : "text-destructive"
                  }
                >
                  {item.level}
                </span>
                {item.href ? (
                  <a
                    className="underline underline-offset-2"
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {item.text} ↗
                  </a>
                ) : (
                  <span>{item.text}</span>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
