"use client";

import { useState } from "react";
import { FilterBar, type Filters } from "@/components/FilterBar";
import { CompanyCard } from "@/components/CompanyCard";
import type { Company } from "@/lib/db";

function applyFilters(companies: Company[], f: Filters): Company[] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - parseInt(f.days));

  return companies.filter((c) => {
    if (f.source !== "all" && c.accelerator !== f.source) return false;

    if (new Date(c.date_filed) < cutoff) return false;

    if (f.amount !== "any") {
      const amt = c.amount_raised;
      if (f.amount === "0-1") {
        if (amt === null || amt === 0 || amt >= 1_000_000) return false;
      } else if (f.amount === "1-10") {
        if (amt === null || amt < 1_000_000 || amt >= 10_000_000) return false;
      } else if (f.amount === "10-100") {
        if (amt === null || amt < 10_000_000 || amt > 100_000_000) return false;
      }
    }

    return true;
  });
}

export function FeedClient({ companies }: { companies: Company[] }) {
  const [filters, setFilters] = useState<Filters>({
    source: "all",
    days: "90",
    amount: "any",
  });

  const visible = applyFilters(companies, filters);

  return (
    <>
      <FilterBar filters={filters} onChange={setFilters} />
      <p className="text-sm text-muted-foreground mb-4">
        {visible.length} {visible.length === 1 ? "company" : "companies"}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map((c) => (
          <CompanyCard key={c.id} company={c} />
        ))}
      </div>
      {visible.length === 0 && (
        <p className="text-muted-foreground text-sm text-center py-12">
          No companies match the current filters.
        </p>
      )}
    </>
  );
}
