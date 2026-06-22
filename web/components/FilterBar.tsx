"use client";

import { Button } from "@/components/ui/button";

export type Filters = {
  sources: string[];
  hiring: string[];
  daysMax: number | null;
  amountMax: number | null;
};

export const DEFAULT_FILTERS: Filters = {
  sources: [],
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

export function FilterBar({ filters, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-8 mb-8">
      <div>
        <p className="text-xs text-muted-foreground mb-2 font-medium">Source</p>
        <Pills
          values={filters.sources}
          onChange={(v) => onChange({ ...filters, sources: v })}
          options={[
            ["yc", "YC"],
            ["a16z", "a16z"],
            ["sequoia", "Sequoia"],
            ["pear", "Pear"],
            ["lightspeed", "Lightspeed"],
            ["techstars", "Techstars"],
          ]}
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
