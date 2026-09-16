"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { Radar, Bookmark, ChevronLeft, ChevronRight } from "lucide-react";
import { FilterBar, HiringFilterBar } from "@/components/FilterBar";
import { CompanyCard } from "@/components/CompanyCard";
import { useBookmarks } from "@/lib/useBookmarks";
import type { Company } from "@/lib/db";
import {
  applyFilters,
  applyHiringFilters,
  byDateDesc,
  byHiringDate,
  DEFAULT_FILTERS,
  type Filters,
} from "@/lib/feed";

const PAGE_SIZE = 15;

function getPageNumbers(page: number, totalPages: number): (number | "...")[] {
  const pages: (number | "...")[] = [];
  const addPage = (p: number) => pages.push(p);

  addPage(1);
  if (page > 4) pages.push("...");
  for (let p = Math.max(2, page - 2); p <= Math.min(totalPages - 1, page + 2); p++) {
    addPage(p);
  }
  if (page < totalPages - 3) pages.push("...");
  if (totalPages > 1) addPage(totalPages);

  return pages;
}

function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  const pageNumbers = getPageNumbers(page, totalPages);

  return (
    <div className="flex items-center justify-center gap-2 mt-8">
      <button
        onClick={() => onPage(Math.max(1, page - 1))}
        disabled={page === 1}
        className="flex items-center gap-1 h-8 px-3 rounded-lg border border-border bg-background text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:pointer-events-none transition-colors"
      >
        <ChevronLeft size={16} />
        Prev
      </button>

      {pageNumbers.map((p, i) =>
        p === "..." ? (
          <span key={`ellipsis-${i}`} className="px-1 text-sm text-muted-foreground">
            ...
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onPage(p)}
            className={`h-8 min-w-8 px-2.5 rounded-lg border text-sm font-medium tabular-nums transition-colors ${
              p === page
                ? "border-foreground bg-foreground text-background"
                : "border-border bg-background text-foreground hover:bg-muted"
            }`}
          >
            {p}
          </button>
        )
      )}

      <button
        onClick={() => onPage(Math.min(totalPages, page + 1))}
        disabled={page === totalPages}
        className="flex items-center gap-1 h-8 px-3 rounded-lg border border-border bg-background text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:pointer-events-none transition-colors"
      >
        Next
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

export function FeedClient({
  companies,
  hiringCompanies,
}: {
  companies: Company[];
  hiringCompanies: Company[];
}) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [hiringAccelerators, setHiringAccelerators] = useState<string[]>([]);
  const [hiringRoleTypes, setHiringRoleTypes] = useState<string[]>([]);
  const [hiringRoleLevels, setHiringRoleLevels] = useState<string[]>([]);
  const [hiringVerticals, setHiringVerticals] = useState<string[]>([]);
  const [tab, setTab] = useState<"raised" | "hiring">("raised");
  const [view, setView] = useState<"feed" | "bookmarks">("feed");
  const [raisedPage, setRaisedPage] = useState(1);
  const [hiringPage, setHiringPage] = useState(1);
  const { toggle, isBookmarked } = useBookmarks();
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [raisedPage, hiringPage]);

  function handleFiltersChange(f: Filters) {
    setFilters(f);
    setRaisedPage(1);
  }

  const visible = useMemo(() => applyFilters(companies, filters), [companies, filters]);
  const recent = useMemo(() => [...visible].sort(byDateDesc), [visible]);

  const raisedTotalPages = Math.ceil(recent.length / PAGE_SIZE);
  const pagedRecent = useMemo(
    () => recent.slice((raisedPage - 1) * PAGE_SIZE, raisedPage * PAGE_SIZE),
    [raisedPage, recent],
  );

  const filteredHiring = useMemo(
    () => applyHiringFilters(
      hiringCompanies,
      hiringAccelerators,
      hiringRoleTypes,
      hiringRoleLevels,
      hiringVerticals,
    ).sort(byHiringDate),
    [hiringAccelerators, hiringCompanies, hiringRoleLevels, hiringRoleTypes, hiringVerticals],
  );
  const hiringTotalPages = Math.ceil(filteredHiring.length / PAGE_SIZE);
  const pagedHiring = useMemo(
    () => filteredHiring.slice((hiringPage - 1) * PAGE_SIZE, hiringPage * PAGE_SIZE),
    [filteredHiring, hiringPage],
  );

  const savedCompanies = useMemo(
    () => companies.filter((company) => isBookmarked(company.id)).sort(byDateDesc),
    [companies, isBookmarked],
  );

  return (
    <>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1
            className={`text-2xl font-bold flex items-center gap-2 ${view === "bookmarks" ? "cursor-pointer hover:opacity-70 transition-opacity" : ""}`}
            onClick={() => view === "bookmarks" && setView("feed")}
          >
            <Radar className="text-red-500" size={26} />
            Radar
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            hot & recently funded startups · updates daily
          </p>
        </div>

        <button
          onClick={() => setView((v) => (v === "bookmarks" ? "feed" : "bookmarks"))}
          title={view === "bookmarks" ? "Back to feed" : "Saved companies"}
          className={`mt-1 p-1.5 rounded-md transition-colors hover:bg-muted ${
            view === "bookmarks" ? "text-foreground" : "text-muted-foreground"
          }`}
        >
          <Bookmark
            size={20}
            fill={view === "bookmarks" ? "currentColor" : "none"}
          />
        </button>
      </div>

      {view === "bookmarks" ? (
        <div>
          {savedCompanies.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-12">
              No saved companies yet. Click the bookmark icon on any card.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground mb-6">
                {savedCompanies.length} saved {savedCompanies.length === 1 ? "company" : "companies"}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {savedCompanies.map((c) => (
                  <CompanyCard
                    key={c.id}
                    company={c}
                    isBookmarked={isBookmarked(c.id)}
                    onToggleBookmark={() => toggle(c.id)}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        <>
          <div className="flex gap-1 mb-6 border-b border-border">
            <button
              onClick={() => setTab("raised")}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                tab === "raised"
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Raised
              <span className="ml-1.5 text-xs text-muted-foreground">{visible.length}</span>
            </button>
            <button
              onClick={() => setTab("hiring")}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                tab === "hiring"
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Actively Hiring
              <span className="ml-1.5 text-xs text-muted-foreground">{filteredHiring.length}</span>
            </button>
          </div>

          {tab === "raised" ? (
            <>
              <FilterBar filters={filters} onChange={handleFiltersChange} />

              {visible.length === 0 && (
                <p className="text-muted-foreground text-sm text-center py-12">
                  No companies match the current filters.
                </p>
              )}

              <div className="space-y-10">
                {recent.length > 0 && (
                  <div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {pagedRecent.map((c) => (
                        <CompanyCard
                          key={c.id}
                          company={c}
                          isBookmarked={isBookmarked(c.id)}
                          onToggleBookmark={() => toggle(c.id)}
                        />
                      ))}
                    </div>
                    <Pagination page={raisedPage} totalPages={raisedTotalPages} onPage={setRaisedPage} />
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <HiringFilterBar
                accelerators={hiringAccelerators}
                roleTypes={hiringRoleTypes}
                roleLevels={hiringRoleLevels}
                verticals={hiringVerticals}
                onAccelerators={(v) => { setHiringAccelerators(v); setHiringPage(1); }}
                onRoleTypes={(v) => { setHiringRoleTypes(v); setHiringPage(1); }}
                onRoleLevels={(v) => { setHiringRoleLevels(v); setHiringPage(1); }}
                onVerticals={(v) => { setHiringVerticals(v); setHiringPage(1); }}
              />
              {filteredHiring.length === 0 ? (
                <p className="text-muted-foreground text-sm text-center py-12">
                  No companies match the current filters.
                </p>
              ) : (
                <div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {pagedHiring.map((c) => (
                      <CompanyCard
                        key={c.id}
                        company={c}
                        isBookmarked={isBookmarked(c.id)}
                        onToggleBookmark={() => toggle(c.id)}
                        hideBatch
                        hiringMode
                      />
                    ))}
                  </div>
                  <Pagination page={hiringPage} totalPages={hiringTotalPages} onPage={setHiringPage} />
                </div>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
