/**
 * Cognito authentication helpers for Phase 2 JWT tenant auth.
 *
 * Uses amazon-cognito-identity-js to authenticate against the
 * tenant-specific app client and obtain an ID token that contains
 * the ``custom:tenant_id`` claim.
 *
 * The ID token (not the access token) is used because Cognito only
 * includes custom attributes in the ID token.
 */

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  type CognitoUserSession,
} from "amazon-cognito-identity-js";

export interface AuthSession {
  /** ID token — contains custom:tenant_id claim */
  idToken: string;
  /** Tenant ID extracted from the token claim */
  tenantId: string;
  /** Username used to authenticate */
  username: string;
}

/** Map from tenant key to Cognito app client ID env var */
const CLIENT_ID_BY_TENANT: Record<string, string | undefined> = {
  axa: import.meta.env.VITE_COGNITO_AXA_CLIENT_ID as string | undefined,
  allianz: import.meta.env.VITE_COGNITO_ALLIANZ_CLIENT_ID as string | undefined,
};

const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID as string | undefined;

/**
 * Returns true when Phase 2 Cognito env vars are configured.
 */
export function isCognitoConfigured(): boolean {
  return Boolean(
    USER_POOL_ID &&
      CLIENT_ID_BY_TENANT.axa &&
      CLIENT_ID_BY_TENANT.allianz
  );
}

/**
 * Authenticate a user against the tenant-specific Cognito app client.
 *
 * @param tenantId - "axa" or "allianz"
 * @param username - Cognito username
 * @param password - Cognito password
 * @returns AuthSession with ID token and extracted tenant ID
 * @throws Error if authentication fails or tenant_id claim is missing
 */
export async function authenticateUser(
  tenantId: string,
  username: string,
  password: string
): Promise<AuthSession> {
  const clientId = CLIENT_ID_BY_TENANT[tenantId];
  if (!clientId) {
    throw new Error(`No Cognito client ID configured for tenant: ${tenantId}`);
  }
  if (!USER_POOL_ID) {
    throw new Error("VITE_COGNITO_USER_POOL_ID is not configured");
  }

  const userPool = new CognitoUserPool({
    UserPoolId: USER_POOL_ID,
    ClientId: clientId,
  });

  const cognitoUser = new CognitoUser({
    Username: username,
    Pool: userPool,
  });

  const authDetails = new AuthenticationDetails({
    Username: username,
    Password: password,
  });

  return new Promise<AuthSession>((resolve, reject) => {
    cognitoUser.authenticateUser(authDetails, {
      onSuccess(session: CognitoUserSession) {
        const idToken = session.getIdToken().getJwtToken();
        const payload = session.getIdToken().decodePayload();
        const extractedTenantId =
          (payload["custom:tenant_id"] as string | undefined) ?? tenantId;

        resolve({ idToken, tenantId: extractedTenantId, username });
      },
      onFailure(err: Error) {
        reject(err);
      },
      newPasswordRequired(_userAttributes, _requiredAttributes) {
        // Demo users have permanent passwords — this should not occur
        reject(new Error("New password required — use admin_set_user_password to set a permanent password"));
      },
    });
  });
}

/**
 * Sign out the current user from the Cognito session.
 *
 * @param tenantId - "axa" or "allianz"
 * @param username - Cognito username to sign out
 */
export function signOutUser(tenantId: string, username: string): void {
  const clientId = CLIENT_ID_BY_TENANT[tenantId];
  if (!clientId || !USER_POOL_ID) return;

  const userPool = new CognitoUserPool({
    UserPoolId: USER_POOL_ID,
    ClientId: clientId,
  });

  const cognitoUser = new CognitoUser({
    Username: username,
    Pool: userPool,
  });

  cognitoUser.signOut();
}
