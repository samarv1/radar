"use client";

import { useState, useMemo } from "react";
import { FilterBar, DEFAULT_FILTERS, type Filters } from "@/components/FilterBar";
import { CompanyCard } from "@/components/CompanyCard";
import type { Company } from "@/lib/db";

const SIX_MONTHS_MS = 180 * 24 * 60 * 60 * 1000;

function hiringStatus(c: Company): "yes" | "no" | "unknown" {
  const hasData = c.careers_ats && c.careers_ats !== "not_found";
  if (!hasData) return "unknown";
  const total = c.eng_count + c.gtm_count + c.product_count + c.other_count;
  return total > 0 ? "yes" : "no";
}

function applyFilters(companies: Company[], f: Filters): Company[] {
  return companies.filter((c) => {
    if (f.sources.length > 0 && !f.sources.includes(c.accelerator)) return false;
    if (f.hiring.length > 0 && !f.hiring.includes(hiringStatus(c))) return false;

    if (f.daysMax !== null) {
      const daysAgo = (Date.now() - new Date(c.date_filed).getTime()) / (1000 * 60 * 60 * 24);
      if (daysAgo > f.daysMax) return false;
    }

    if (f.amountMax !== null) {
      if (c.amount_raised === null || c.amount_raised > f.amountMax) return false;
    }

    return true;
  });
}

function byDateDesc(a: Company, b: Company) {
  return new Date(b.date_filed).getTime() - new Date(a.date_filed).getTime();
}

export function FeedClient({ companies }: { companies: Company[] }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [expandedOld, setExpandedOld] = useState(false);

  const visible = applyFilters(companies, filters);
  // eslint-disable-next-line react-hooks/purity
  const now = useMemo(() => Date.now(), []);

  const recent = visible
    .filter((c) => now - new Date(c.date_filed).getTime() < SIX_MONTHS_MS)
    .sort(byDateDesc);

  const oldCompanies = visible
    .filter((c) => now - new Date(c.date_filed).getTime() >= SIX_MONTHS_MS)
    .sort(byDateDesc);

  return (
    <>
      <FilterBar filters={filters} onChange={setFilters} />
      <p className="text-sm text-muted-foreground mb-6">
        {visible.length} {visible.length === 1 ? "company" : "companies"}
      </p>

      {visible.length === 0 && (
        <p className="text-muted-foreground text-sm text-center py-12">
          No companies match the current filters.
        </p>
      )}

      <div className="space-y-10">
        {recent.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {recent.map((c) => (
              <CompanyCard key={c.id} company={c} />
            ))}
          </div>
        )}

        {oldCompanies.length > 0 && (
          <div>
            <button
              onClick={() => setExpandedOld((prev) => !prev)}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors mb-4"
            >
              <span>{expandedOld ? "▾" : "▸"}</span>
              Funded 6+ months ago ({oldCompanies.length})
            </button>

            {expandedOld && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {oldCompanies.map((c) => (
                  <CompanyCard key={c.id} company={c} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
