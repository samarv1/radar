"use client";

import { useState } from "react";
import { FilterBar, type Filters } from "@/components/FilterBar";
import { CompanyCard } from "@/components/CompanyCard";
import type { Company } from "@/lib/db";

const SOURCE_ORDER = ["yc", "a16z", "sequoia", "pear", "lightspeed", "techstars"];
const SOURCE_LABELS: Record<string, string> = {
  yc: "Y Combinator",
  a16z: "a16z",
  sequoia: "Sequoia",
  pear: "Pear VC",
  lightspeed: "Lightspeed",
  techstars: "Techstars",
};

const SIX_MONTHS_MS = 180 * 24 * 60 * 60 * 1000;

function applyFilters(companies: Company[], f: Filters): Company[] {
  return companies.filter((c) => {
    if (f.source !== "all" && c.accelerator !== f.source) return false;
    if (f.days !== "all") {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - parseInt(f.days));
      if (new Date(c.date_filed) < cutoff) return false;
    }
    if (f.amount !== "any") {
      const amt = c.amount_raised;
      if (f.amount === "0-1") {
        if (amt === null || amt < 10_000 || amt >= 1_000_000) return false;
      } else if (f.amount === "1-10") {
        if (amt === null || amt < 1_000_000 || amt >= 10_000_000) return false;
      } else if (f.amount === "10-100") {
        if (amt === null || amt < 10_000_000 || amt > 100_000_000) return false;
      }
    }
    return true;
  });
}

function byDateDesc(a: Company, b: Company) {
  return new Date(b.date_filed).getTime() - new Date(a.date_filed).getTime();
}

export function FeedClient({ companies }: { companies: Company[] }) {
  const [filters, setFilters] = useState<Filters>({
    source: "all",
    days: "all",
    amount: "any",
  });
  const [expandedOld, setExpandedOld] = useState<Record<string, boolean>>({});

  const visible = applyFilters(companies, filters);
  const now = Date.now();

  const sections = SOURCE_ORDER
    .map((src) => {
      const all = visible
        .filter((c) => c.accelerator === src)
        .sort(byDateDesc);
      const recent = all.filter((c) => now - new Date(c.date_filed).getTime() < SIX_MONTHS_MS);
      const old = all.filter((c) => now - new Date(c.date_filed).getTime() >= SIX_MONTHS_MS);
      return { key: src, label: SOURCE_LABELS[src] ?? src, recent, old };
    })
    .filter((s) => s.recent.length > 0 || s.old.length > 0);

  return (
    <>
      <FilterBar filters={filters} onChange={setFilters} />
      <p className="text-sm text-muted-foreground mb-6">
        {visible.length} {visible.length === 1 ? "company" : "companies"}
      </p>

      {sections.length === 0 && (
        <p className="text-muted-foreground text-sm text-center py-12">
          No companies match the current filters.
        </p>
      )}

      <div className="space-y-10">
        {sections.map((section) => (
          <div key={section.key}>
            <div className="flex items-baseline gap-2 mb-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {section.label}
              </h2>
              <span className="text-xs text-muted-foreground">
                {section.recent.length + section.old.length}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {section.recent.map((c) => (
                <CompanyCard key={c.id} company={c} />
              ))}
            </div>

            {section.old.length > 0 && (
              <div className="mt-4">
                <button
                  onClick={() =>
                    setExpandedOld((prev) => ({ ...prev, [section.key]: !prev[section.key] }))
                  }
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                >
                  <span>{expandedOld[section.key] ? "▾" : "▸"}</span>
                  Funded 6+ months ago ({section.old.length})
                </button>

                {expandedOld[section.key] && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-3">
                    {section.old.map((c) => (
                      <CompanyCard key={c.id} company={c} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
