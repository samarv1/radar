"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

export type Filters = {
  accelerators: string[];
  hiring: string[];
  days: number[];
  amounts: number[];
  verticals: string[];
  rounds: string[];
};

export const DEFAULT_FILTERS: Filters = {
  accelerators: [],
  hiring: [],
  days: [],
  amounts: [],
  verticals: [],
  rounds: [],
};

export function normalizeRoundType(rt: string | null): string {
  if (!rt) return "unknown";
  const s = rt.toLowerCase().trim();
  if (s.includes("pre") || s === "seed") return "seed";
  if (s.includes("series a")) return "series_a";
  if (s.includes("series b")) return "series_b";
  if (s.includes("series c") || s.includes("series d") || s.includes("series e")) return "series_c";
  return "unknown";
}

const ROUND_OPTIONS: [string, string][] = [
  ["seed", "Seed / Pre-Seed"],
  ["series_a", "Series A"],
  ["series_b", "Series B"],
  ["series_c", "Series C+"],
  ["unknown", "Unknown"],
];

export const VERTICAL_KEYWORDS: Record<string, string[]> = {
  ai:       ["ai", "artificial intelligence", "machine learning", "generative ai", "llm", "deep learning", "nlp", "computer vision"],
  fintech:  ["fintech", "payments", "crypto", "blockchain", "banking", "insurtech", "lending", "wealth"],
  health:   ["health", "biotech", "pharma", "medical", "clinical", "genomics", "drug", "therapy", "mental health"],
  b2b:      ["saas", "b2b", "enterprise"],
  devtools: ["developer tools", "developer tool", "infrastructure", "open source", "devops", "security", "observability", "api", "platform engineering"],
  climate:  ["climate", "cleantech", "sustainability", "energy", "carbon", "renewable"],
  consumer: ["consumer", "e-commerce", "marketplace", "gaming", "social", "entertainment", "media", "retail"],
  edtech:   ["education", "edtech", "upskilling"],
  hardware: ["hardware", "robotics", "iot", "internet of things", "manufacturing", "semiconductors", "aerospace"],
};

export function tagMatchesKeyword(tag: string, kw: string): boolean {
  const t = tag.toLowerCase();
  const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Left-boundary match: kw must start at beginning of tag or after a non-word char.
  // This catches "Healthcare" → "health" (prefix) while blocking "Biomedical" → "media" (infix).
  return new RegExp(`(?:^|\\W)${escaped}`).test(t);
}

const VERTICAL_OPTIONS: [string, string][] = [
  ["ai", "AI / ML"],
  ["fintech", "Fintech"],
  ["health", "Health"],
  ["b2b", "B2B / SaaS"],
  ["devtools", "Dev Tools"],
  ["climate", "Climate"],
  ["consumer", "Consumer"],
  ["edtech", "EdTech"],
  ["hardware", "Hardware"],
  ["unknown", "Unknown"],
];

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

function CheckboxList({
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
    <div className="flex flex-col min-w-[150px]">
      {options.map(([val, label]) => {
        const checked = values.includes(val);
        return (
          <button
            key={val}
            onClick={() => toggle(val)}
            className="flex items-center gap-2.5 px-2 py-1.5 rounded-md hover:bg-muted text-sm text-left w-full transition-colors"
          >
            <div className={`w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors ${checked ? "bg-foreground border-foreground" : "border-border"}`}>
              {checked && <Check size={10} className="text-background" strokeWidth={3} />}
            </div>
            {label}
          </button>
        );
      })}
    </div>
  );
}

function NumberCheckboxList({
  options,
  values,
  onChange,
}: {
  options: [number, string][];
  values: number[];
  onChange: (v: number[]) => void;
}) {
  function toggle(val: number) {
    onChange(
      values.includes(val) ? values.filter((v) => v !== val) : [...values, val]
    );
  }
  return (
    <div className="flex flex-col min-w-[120px]">
      {options.map(([val, label]) => {
        const checked = values.includes(val);
        return (
          <button
            key={val}
            onClick={() => toggle(val)}
            className="flex items-center gap-2.5 px-2 py-1.5 rounded-md hover:bg-muted text-sm text-left w-full transition-colors"
          >
            <div className={`w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors ${checked ? "bg-foreground border-foreground" : "border-border"}`}>
              {checked && <Check size={10} className="text-background" strokeWidth={3} />}
            </div>
            {label}
          </button>
        );
      })}
    </div>
  );
}

function FilterDropdown({
  label,
  activeCount,
  children,
}: {
  label: string;
  activeCount: number;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const active = activeCount > 0;

  return (
    <div ref={ref} className="relative">
      <Button
        size="sm"
        variant={active ? "default" : "outline"}
        onClick={() => setOpen((o) => !o)}
        className="gap-1.5"
      >
        {label}
        {active && (
          <span className="bg-white/25 text-[10px] font-semibold leading-none rounded-full px-1.5 py-0.5">
            {activeCount}
          </span>
        )}
        <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </Button>

      {open && (
        <div className="absolute top-full mt-1.5 left-0 z-50 bg-background border border-border rounded-lg shadow-lg p-3 min-w-max">
          {children}
        </div>
      )}
    </div>
  );
}

type Props = {
  filters: Filters;
  onChange: (f: Filters) => void;
};

export function FilterBar({ filters, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 mb-8">
      <FilterDropdown label="Accelerator" activeCount={filters.accelerators.length}>
        <CheckboxList
          values={filters.accelerators}
          onChange={(v) => onChange({ ...filters, accelerators: v })}
          options={ACCELERATOR_OPTIONS}
        />
      </FilterDropdown>

      <FilterDropdown label="Vertical" activeCount={filters.verticals.length}>
        <CheckboxList
          values={filters.verticals}
          onChange={(v) => onChange({ ...filters, verticals: v })}
          options={VERTICAL_OPTIONS}
        />
      </FilterDropdown>

      <FilterDropdown label="Hiring" activeCount={filters.hiring.length}>
        <CheckboxList
          values={filters.hiring}
          onChange={(v) => onChange({ ...filters, hiring: v })}
          options={[
            ["yes", "Yes"],
            ["no", "No"],
            ["unknown", "Unknown"],
          ]}
        />
      </FilterDropdown>

      <FilterDropdown label="Filed within" activeCount={filters.days.length}>
        <NumberCheckboxList
          options={[[30, "30d"], [60, "60d"], [90, "90d"]]}
          values={filters.days}
          onChange={(v) => onChange({ ...filters, days: v })}
        />
      </FilterDropdown>

      <FilterDropdown label="Amount raised" activeCount={filters.amounts.length}>
        <NumberCheckboxList
          options={[
            [1_000_000, "<$1M"],
            [10_000_000, "<$10M"],
            [100_000_000, "<$100M"],
          ]}
          values={filters.amounts}
          onChange={(v) => onChange({ ...filters, amounts: v })}
        />
      </FilterDropdown>

      <FilterDropdown label="Round" activeCount={filters.rounds.length}>
        <CheckboxList
          values={filters.rounds}
          onChange={(v) => onChange({ ...filters, rounds: v })}
          options={ROUND_OPTIONS}
        />
      </FilterDropdown>
    </div>
  );
}

export function HiringFilterBar({
  accelerators,
  roleTypes,
  roleLevels,
  verticals,
  onAccelerators,
  onRoleTypes,
  onRoleLevels,
  onVerticals,
}: {
  accelerators: string[];
  roleTypes: string[];
  roleLevels: string[];
  verticals: string[];
  onAccelerators: (v: string[]) => void;
  onRoleTypes: (v: string[]) => void;
  onRoleLevels: (v: string[]) => void;
  onVerticals: (v: string[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-8">
      <FilterDropdown label="Accelerator" activeCount={accelerators.length}>
        <CheckboxList values={accelerators} onChange={onAccelerators} options={HIRING_ACCELERATOR_OPTIONS} />
      </FilterDropdown>

      <FilterDropdown label="Vertical" activeCount={verticals.length}>
        <CheckboxList values={verticals} onChange={onVerticals} options={VERTICAL_OPTIONS} />
      </FilterDropdown>

      <FilterDropdown label="Role Type" activeCount={roleTypes.length}>
        <CheckboxList values={roleTypes} onChange={onRoleTypes} options={ROLE_TYPE_OPTIONS} />
      </FilterDropdown>

      <FilterDropdown label="Role Level" activeCount={roleLevels.length}>
        <CheckboxList values={roleLevels} onChange={onRoleLevels} options={ROLE_LEVEL_OPTIONS} />
      </FilterDropdown>
    </div>
  );
}
