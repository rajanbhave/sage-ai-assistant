/**
 * Build-time configuration for the JWT-passthrough demo stage.
 *
 * The stage performs one deliberate cross-lane rejection probe, which sends the
 * current session bearer to the other lane's Agent Runtime endpoint expecting a
 * managed denial. That is demonstration behaviour, not product behaviour, so it
 * is gated on an explicit build-time flag and must stay disabled in any build
 * that serves real users.
 */

/** True only when the operator explicitly enabled the demo stage at build time. */
export const DEMO_STAGE_ENABLED = import.meta.env.VITE_DEMO_STAGE === "true";

const REGION = (import.meta.env.VITE_AWS_REGION ?? "").trim();

const LOG_GROUPS: Readonly<Record<string, string>> = {
  Tenant_A: (import.meta.env.VITE_TENANT_A_LOG_GROUP ?? "").trim(),
  Tenant_B: (import.meta.env.VITE_TENANT_B_LOG_GROUP ?? "").trim(),
};

/** Logs Insights deep links escape the percent signs of encoded values as `*`. */
function encodeInsightsValue(value: string): string {
  return encodeURIComponent(value).replace(/%/g, "*");
}

/**
 * Build a CloudWatch Logs Insights deep link that searches one correlation ID.
 *
 * Returns null when the region or the lane log group is not configured, so the
 * evidence feed can state that the link is unavailable rather than invent one.
 */
export function buildLogsInsightsUrl(
  laneId: string,
  correlationId: string
): string | null {
  const logGroup = LOG_GROUPS[laneId] ?? "";
  if (!REGION || !logGroup || !/^[0-9a-f]{32}$/.test(correlationId)) return null;

  const query = encodeInsightsValue(
    [
      "fields @timestamp, @message",
      `filter @message like "${correlationId}"`,
      "sort @timestamp desc",
      "limit 50",
    ].join("\n| ")
  );

  return (
    `https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}` +
    "#logsV2:logs-insights$3FqueryDetail$3D~(end~0~start~-3600~timeType~'RELATIVE" +
    `~unit~'seconds~editorString~'${query}` +
    `~source~(~'${encodeInsightsValue(logGroup)}))`
  );
}
