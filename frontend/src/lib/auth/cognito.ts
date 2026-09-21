import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  type CognitoUserSession,
} from "amazon-cognito-identity-js";
import { AuthenticationArtifact } from "./artifact";

export type LaneId = "Tenant_A" | "Tenant_B";

export const TENANT_DISPLAY_NAMES = {
  Tenant_A: "AXA",
  Tenant_B: "Allianz",
} as const satisfies Record<LaneId, string>;

export interface TrustedLaneRecord {
  readonly laneId: LaneId;
  readonly tenantId: LaneId;
  readonly userPoolId: string;
  readonly appClientId: string;
  readonly issuer: string;
  readonly agentRuntimeEndpoint: string;
  readonly expectedTenantClaim: LaneId;
}

export interface AuthSession {
  readonly lane: TrustedLaneRecord;
  readonly accessToken: AuthenticationArtifact;
  readonly subject: string;
  readonly tenantId: LaneId;
  readonly expiresAt: number;
  readonly sessionId: string;
  readonly username: string;
}

const CANONICAL_TENANT_CLAIM = "custom:tenant_id";

const TRUSTED_LANES = Object.freeze([
  Object.freeze({
    laneId: "Tenant_A",
    tenantId: "Tenant_A",
    userPoolId:
      (import.meta.env.VITE_TENANT_A_USER_POOL_ID as string | undefined) ?? "",
    appClientId:
      (import.meta.env.VITE_TENANT_A_APP_CLIENT_ID as string | undefined) ?? "",
    issuer: (import.meta.env.VITE_TENANT_A_ISSUER as string | undefined) ?? "",
    agentRuntimeEndpoint:
      (import.meta.env.VITE_TENANT_A_AGENT_RUNTIME_ENDPOINT as
        | string
        | undefined) ?? "",
    expectedTenantClaim: "Tenant_A",
  }),
  Object.freeze({
    laneId: "Tenant_B",
    tenantId: "Tenant_B",
    userPoolId:
      (import.meta.env.VITE_TENANT_B_USER_POOL_ID as string | undefined) ?? "",
    appClientId:
      (import.meta.env.VITE_TENANT_B_APP_CLIENT_ID as string | undefined) ?? "",
    issuer: (import.meta.env.VITE_TENANT_B_ISSUER as string | undefined) ?? "",
    agentRuntimeEndpoint:
      (import.meta.env.VITE_TENANT_B_AGENT_RUNTIME_ENDPOINT as
        | string
        | undefined) ?? "",
    expectedTenantClaim: "Tenant_B",
  }),
] as const satisfies readonly [TrustedLaneRecord, TrustedLaneRecord]);

function invalidLane(): Error {
  return new Error("The selected authentication lane is invalid.");
}

function invalidSession(): Error {
  return new Error("A valid authentication session is required.");
}

function assertTrustedLaneRegistry(): void {
  const requiredFields: (keyof Pick<
    TrustedLaneRecord,
    | "userPoolId"
    | "appClientId"
    | "issuer"
    | "agentRuntimeEndpoint"
    | "expectedTenantClaim"
  >)[] = [
    "userPoolId",
    "appClientId",
    "issuer",
    "agentRuntimeEndpoint",
    "expectedTenantClaim",
  ];

  if (
    TRUSTED_LANES.length !== 2 ||
    TRUSTED_LANES[0].laneId !== "Tenant_A" ||
    TRUSTED_LANES[1].laneId !== "Tenant_B"
  ) {
    throw invalidLane();
  }

  for (const field of requiredFields) {
    const values = TRUSTED_LANES.map((lane) => lane[field]);
    if (values.some((value) => !value.trim()) || new Set(values).size !== 2) {
      throw invalidLane();
    }
  }
}

/** Resolve exactly one immutable deployment-owned Tenant A or Tenant B lane. */
export function resolveTrustedLane(laneId: string): TrustedLaneRecord {
  if (laneId !== "Tenant_A" && laneId !== "Tenant_B") {
    throw invalidLane();
  }

  assertTrustedLaneRegistry();
  const matches = TRUSTED_LANES.filter((lane) => lane.laneId === laneId);
  if (matches.length !== 1) {
    throw invalidLane();
  }
  return matches[0]!;
}

function userPoolFor(lane: TrustedLaneRecord): CognitoUserPool {
  return new CognitoUserPool({
    UserPoolId: lane.userPoolId,
    ClientId: lane.appClientId,
  });
}

/** Establish a lane-bound browser session from a Cognito access token. */
export function establishSession(
  lane: TrustedLaneRecord,
  username: string,
  cognitoSession: CognitoUserSession
): AuthSession {
  if (resolveTrustedLane(lane.laneId) !== lane) {
    throw invalidSession();
  }

  let accessToken: string;
  let payload: Record<string, unknown>;
  try {
    const token = cognitoSession.getAccessToken();
    accessToken = token.getJwtToken();
    const decodedPayload = token.decodePayload() as unknown;
    if (
      typeof decodedPayload !== "object" ||
      decodedPayload === null ||
      Array.isArray(decodedPayload)
    ) {
      throw invalidSession();
    }
    payload = decodedPayload as Record<string, unknown>;
  } catch {
    throw invalidSession();
  }

  const subject = payload.sub;
  const tenantId = payload[CANONICAL_TENANT_CLAIM];
  const expiresAt = payload.exp;

  if (
    !accessToken ||
    payload.token_use !== "access" ||
    payload.iss !== lane.issuer ||
    payload.client_id !== lane.appClientId ||
    typeof subject !== "string" ||
    !subject.trim() ||
    tenantId !== lane.expectedTenantClaim ||
    typeof expiresAt !== "number" ||
    !Number.isFinite(expiresAt) ||
    Date.now() >= expiresAt * 1000
  ) {
    throw invalidSession();
  }

  return Object.freeze({
    lane,
    accessToken: new AuthenticationArtifact(accessToken),
    subject,
    tenantId: lane.expectedTenantClaim,
    expiresAt,
    sessionId: crypto.randomUUID(),
    username,
  });
}

/** Authenticate only against the pool and public client assigned to a trusted lane. */
export async function authenticateUser(
  laneId: string,
  username: string,
  password: string
): Promise<AuthSession> {
  const lane = resolveTrustedLane(laneId);
  const cognitoUser = new CognitoUser({
    Username: username,
    Pool: userPoolFor(lane),
  });
  const authDetails = new AuthenticationDetails({
    Username: username,
    Password: password,
  });

  return new Promise<AuthSession>((resolve, reject) => {
    cognitoUser.authenticateUser(authDetails, {
      onSuccess(session: CognitoUserSession) {
        try {
          resolve(establishSession(lane, username, session));
        } catch (error) {
          cognitoUser.signOut();
          reject(error);
        }
      },
      onFailure() {
        reject(new Error("Authentication failed."));
      },
      newPasswordRequired() {
        reject(new Error("Authentication cannot be completed."));
      },
    });
  });
}

/** Return whether two sessions represent the same lane-bound authenticated identity. */
export function hasSameAuthenticationIdentity(
  current: AuthSession,
  candidate: AuthSession
): boolean {
  return (
    current.lane.laneId === candidate.lane.laneId &&
    current.lane.issuer === candidate.lane.issuer &&
    current.lane.appClientId === candidate.lane.appClientId &&
    current.subject === candidate.subject &&
    current.tenantId === candidate.tenantId
  );
}

/** Renew an access token using only browser state from the selected lane's pool. */
export async function renewSession(current: AuthSession): Promise<AuthSession> {
  const lane = resolveTrustedLane(current.lane.laneId);
  if (lane !== current.lane) throw invalidSession();

  const cognitoUser = new CognitoUser({
    Username: current.username,
    Pool: userPoolFor(lane),
  });

  return new Promise<AuthSession>((resolve, reject) => {
    cognitoUser.getSession(
      (sessionError: Error | null, cachedSession: CognitoUserSession | null) => {
        if (sessionError || !cachedSession) {
          reject(invalidSession());
          return;
        }

        cognitoUser.refreshSession(
          cachedSession.getRefreshToken(),
          (refreshError: Error | null, refreshedSession: CognitoUserSession | null) => {
            if (refreshError || !refreshedSession) {
              reject(invalidSession());
              return;
            }

            try {
              const candidate = establishSession(
                lane,
                current.username,
                refreshedSession
              );
              if (!hasSameAuthenticationIdentity(current, candidate)) {
                throw invalidSession();
              }
              resolve(
                Object.freeze({ ...candidate, sessionId: current.sessionId })
              );
            } catch {
              reject(invalidSession());
            }
          }
        );
      }
    );
  });
}

/** Remove browser-owned Cognito credentials for the terminated session. */
export function signOutUser(
  session: Pick<AuthSession, "lane" | "username">
): void {
  const lane = resolveTrustedLane(session.lane.laneId);
  new CognitoUser({
    Username: session.username,
    Pool: userPoolFor(lane),
  }).signOut();
}
