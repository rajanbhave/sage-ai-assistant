/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_TENANT_A_USER_POOL_ID?: string;
  readonly VITE_TENANT_B_USER_POOL_ID?: string;
  readonly VITE_TENANT_A_APP_CLIENT_ID?: string;
  readonly VITE_TENANT_B_APP_CLIENT_ID?: string;
  readonly VITE_TENANT_A_ISSUER?: string;
  readonly VITE_TENANT_B_ISSUER?: string;
  readonly VITE_TENANT_A_AGENT_RUNTIME_ENDPOINT?: string;
  readonly VITE_TENANT_B_AGENT_RUNTIME_ENDPOINT?: string;
  /** Enables the demo stage and its deliberate cross-lane rejection probe. */
  readonly VITE_DEMO_STAGE?: string;
  /** Optional: region used to build CloudWatch evidence links. */
  readonly VITE_AWS_REGION?: string;
  /** Optional: lane log groups used to build CloudWatch evidence links. */
  readonly VITE_TENANT_A_LOG_GROUP?: string;
  readonly VITE_TENANT_B_LOG_GROUP?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
