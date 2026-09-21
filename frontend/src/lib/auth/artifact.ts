export type AuthenticationArtifactProvenance = "access_token";

const ARTIFACT_BRAND = Symbol.for("sage.authentication-artifact.brand");
const ARTIFACT_VALUE = Symbol.for("sage.authentication-artifact.value");

/** Typed credential whose raw value is available only to trusted transport. */
export class AuthenticationArtifact {
  readonly provenance: AuthenticationArtifactProvenance;

  constructor(value: string, provenance: AuthenticationArtifactProvenance = "access_token") {
    if (!value) throw new Error("Authentication artifact value is required.");
    this.provenance = provenance;
    Object.defineProperties(this, {
      [ARTIFACT_BRAND]: { value: true },
      [ARTIFACT_VALUE]: { value },
    });
    Object.freeze(this);
  }
}

export function isAuthenticationArtifact(
  value: unknown
): value is AuthenticationArtifact {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Record<symbol, unknown>)[ARTIFACT_BRAND] === true
  );
}

/** The only Frontend serializer allowed to expose an access token value. */
export function buildAuthorizationHeader(
  artifact: AuthenticationArtifact
): string {
  if (
    !isAuthenticationArtifact(artifact) ||
    artifact.provenance !== "access_token"
  ) {
    throw new Error("A valid access-token artifact is required.");
  }
  return `Bearer ${(artifact as unknown as Record<symbol, string>)[ARTIFACT_VALUE]}`;
}
