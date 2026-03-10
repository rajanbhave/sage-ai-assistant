interface TenantSelectorProps {
  tenantId: string;
  onTenantChange: (tenantId: string) => void;
}

const TENANTS = [
  { value: "axa", label: "AXA" },
  { value: "allianz", label: "Allianz" },
] as const;

export function TenantSelector({ tenantId, onTenantChange }: TenantSelectorProps) {
  return (
    <select
      value={tenantId}
      onChange={(e) => onTenantChange(e.target.value)}
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
