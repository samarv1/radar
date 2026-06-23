"use client";

import { Button } from "@/components/ui/button";

export type Filters = {
  accelerators: string[];
  hiring: string[];
  daysMax: number | null;
  amountMax: number | null;
};

export const DEFAULT_FILTERS: Filters = {
  accelerators: [],
  hiring: [],
  daysMax: null,
  amountMax: null,
};

type Props = {
  filters: Filters;
  onChange: (f: Filters) => void;
};

function Pills({
  options,
  values,
  onChange,
}: {
  options: [string, string][];
  values: string[];
  onChange: (v: string[]) => void;
}) {
  function toggle(val: string) {
    onChange(
      values.includes(val) ? values.filter((v) => v !== val) : [...values, val]
    );
  }
  return (
    <div className="flex gap-1 flex-wrap">
      {options.map(([val, label]) => (
        <Button
          key={val}
          size="sm"
          variant={values.includes(val) ? "default" : "outline"}
          onClick={() => toggle(val)}
        >
          {label}
        </Button>
      ))}
    </div>
  );
}

function SinglePills<T extends string | number>({
  options,
  value,
  onChange,
}: {
  options: [T, string][];
  value: T | null;
  onChange: (v: T | null) => void;
}) {
  return (
    <div className="flex gap-1 flex-wrap">
      {options.map(([val, label]) => (
        <Button
          key={String(val)}
          size="sm"
          variant={value === val ? "default" : "outline"}
          onClick={() => onChange(value === val ? null : val)}
        >
          {label}
        </Button>
      ))}
    </div>
  );
}

const ACCELERATOR_OPTIONS: [string, string][] = [
  ["yc", "YC"],
  ["a16z", "a16z"],
  ["sequoia", "Sequoia"],
  ["pear", "Pear"],
  ["lightspeed", "Lightspeed"],
  ["techstars", "Techstars"],
  ["unknown", "None / Unknown"],
];

const HIRING_ACCELERATOR_OPTIONS: [string, string][] = [
  ["yc", "YC"],
  ["a16z", "a16z"],
  ["sequoia", "Sequoia"],
  ["pear", "Pear"],
  ["lightspeed", "Lightspeed"],
  ["techstars", "Techstars"],
];

const ROLE_TYPE_OPTIONS: [string, string][] = [
  ["eng", "Eng"],
  ["product", "Product"],
  ["gtm", "GTM"],
  ["other", "Other"],
];

const ROLE_LEVEL_OPTIONS: [string, string][] = [
  ["intern", "Intern"],
  ["new_grad", "New Grad"],
  ["experienced", "Other"],
];

export function HiringFilterBar({
  accelerators,
  roleTypes,
  roleLevels,
  onAccelerators,
  onRoleTypes,
  onRoleLevels,
}: {
  accelerators: string[];
  roleTypes: string[];
  roleLevels: string[];
  onAccelerators: (v: string[]) => void;
  onRoleTypes: (v: string[]) => void;
  onRoleLevels: (v: string[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-8 mb-8">
      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Accelerator / Firm</p>
        <Pills values={accelerators} onChange={onAccelerators} options={HIRING_ACCELERATOR_OPTIONS} />
      </div>
      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Role Type</p>
        <Pills values={roleTypes} onChange={onRoleTypes} options={ROLE_TYPE_OPTIONS} />
      </div>
      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Role Level</p>
        <Pills values={roleLevels} onChange={onRoleLevels} options={ROLE_LEVEL_OPTIONS} />
      </div>
    </div>
  );
}

export function FilterBar({ filters, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-8 mb-8">
      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Accelerator / Firm</p>
        <Pills
          values={filters.accelerators}
          onChange={(v) => onChange({ ...filters, accelerators: v })}
          options={ACCELERATOR_OPTIONS}
        />
      </div>

      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Hiring</p>
        <Pills
          values={filters.hiring}
          onChange={(v) => onChange({ ...filters, hiring: v })}
          options={[
            ["yes", "Yes"],
            ["no", "No"],
            ["unknown", "Unknown"],
          ]}
        />
      </div>

      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Filed within</p>
        <SinglePills
          options={[[30, "30d"], [60, "60d"], [90, "90d"]] as [number, string][]}
          value={filters.daysMax}
          onChange={(v) => onChange({ ...filters, daysMax: v })}
        />
      </div>

      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Amount raised</p>
        <SinglePills
          options={[
            [1_000_000, "<$1M"],
            [10_000_000, "<$10M"],
            [100_000_000, "<$100M"],
          ] as [number, string][]}
          value={filters.amountMax}
          onChange={(v) => onChange({ ...filters, amountMax: v })}
        />
      </div>
    </div>
  );
}
