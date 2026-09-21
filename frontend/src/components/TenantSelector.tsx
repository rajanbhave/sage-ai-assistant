import { TENANT_DISPLAY_NAMES, type LaneId } from "@/lib/auth/cognito";

interface TenantSelectorProps {
  tenantId: LaneId;
  onTenantChange: (tenantId: LaneId) => void;
}

const TENANTS = [
  { value: "Tenant_A", label: TENANT_DISPLAY_NAMES.Tenant_A },
  { value: "Tenant_B", label: TENANT_DISPLAY_NAMES.Tenant_B },
] as const satisfies readonly { value: LaneId; label: string }[];

export function TenantSelector({ tenantId, onTenantChange }: TenantSelectorProps) {
  return (
    <select
      value={tenantId}
      onChange={(e) => {
        const value = e.target.value;
        if (value === "Tenant_A" || value === "Tenant_B") onTenantChange(value);
      }}
      className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring cursor-pointer"
    >
      {TENANTS.map(({ value, label }) => (
        <option key={value} value={value}>
          {label}
        </option>
      ))}
    </select>
  );
}
