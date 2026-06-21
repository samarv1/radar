"use client";

import { Button } from "@/components/ui/button";

export type Filters = {
  source: string;
  days: string;
  amount: string;
};

type Props = {
  filters: Filters;
  onChange: (f: Filters) => void;
};

function Pills({
  options,
  value,
  onChange,
}: {
  options: [string, string][];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex gap-1 flex-wrap">
      {options.map(([val, label]) => (
        <Button
          key={val}
          size="sm"
          variant={value === val ? "default" : "outline"}
          onClick={() => onChange(val)}
        >
          {label}
        </Button>
      ))}
    </div>
  );
}

export function FilterBar({ filters, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-6 mb-6">
      <div>
        <p className="text-xs text-muted-foreground mb-1.5 font-medium">Source</p>
        <Pills
          value={filters.source}
          onChange={(v) => onChange({ ...filters, source: v })}
          options={[
            ["all", "All"],
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
        <p className="text-xs text-muted-foreground mb-1.5 font-medium">Filed within</p>
        <Pills
          value={filters.days}
          onChange={(v) => onChange({ ...filters, days: v })}
          options={[
            ["30", "30d"],
            ["60", "60d"],
            ["90", "90d"],
          ]}
        />
      </div>

      <div>
        <p className="text-xs text-muted-foreground mb-1.5 font-medium">Amount raised</p>
        <Pills
          value={filters.amount}
          onChange={(v) => onChange({ ...filters, amount: v })}
          options={[
            ["any", "Any"],
            ["0-1", "<$1M"],
            ["1-10", "$1M–$10M"],
            ["10-100", "$10M–$100M"],
          ]}
        />
      </div>
    </div>
  );
}
