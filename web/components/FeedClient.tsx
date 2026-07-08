"use client";

import { useState, useEffect, useRef } from "react";
import { Radar, Bookmark, ChevronLeft, ChevronRight } from "lucide-react";
import { FilterBar, HiringFilterBar, DEFAULT_FILTERS, VERTICAL_KEYWORDS, tagMatchesKeyword, normalizeRoundType, type Filters } from "@/components/FilterBar";
import { CompanyCard } from "@/components/CompanyCard";
import { useBookmarks } from "@/lib/useBookmarks";
import type { Company } from "@/lib/db";

const PAGE_SIZE = 15;

function hiringStatus(c: Company): "yes" | "no" | "unknown" {
  const hasData = c.careers_ats && c.careers_ats !== "not_found";
  if (!hasData) return "unknown";
  const total = c.eng_count + c.gtm_count + c.product_count + c.other_count;
  return total > 0 ? "yes" : "no";
}

const KNOWN_ACCELERATORS = ["yc", "a16z", "sequoia", "pear", "lightspeed", "techstars"];

function matchesVertical(tags: string[] | null, verticals: string[]): boolean {
  const hasNoTags = !tags || tags.length === 0;
  if (verticals.includes("unknown") && hasNoTags) return true;
  if (hasNoTags) return false;
  return verticals.some(
    (v) =>
      v !== "unknown" &&
      VERTICAL_KEYWORDS[v].some((kw) =>
        tags.some((t) => tagMatchesKeyword(t, kw))
      )
  );
}

function applyFilters(companies: Company[], f: Filters): Company[] {
  return companies.filter((c) => {
    if (f.accelerators.length > 0) {
      const accels = c.accelerators ?? [c.accelerator];
      const isKnown = accels.some(a => KNOWN_ACCELERATORS.includes(a));
      const matchesAccel = accels.some(a => f.accelerators.includes(a));
      const matchesUnknown = f.accelerators.includes("unknown") && !isKnown;
      if (!matchesAccel && !matchesUnknown) return false;
    }

    if (f.hiring.length > 0 && !f.hiring.includes(hiringStatus(c))) return false;

    if (f.days.length > 0) {
      // Calendar-date diff (UTC, midnight-truncated) to match the SQL cutoff
      // in getFeed(), which compares (NOW() AT TIME ZONE 'UTC')::date against
      // date_filed. A raw Date.now() diff includes today's elapsed hours,
      // which pushes borderline rows (filed exactly N days ago) over the
      // threshold and drops them even though the server already included them.
      const today = new Date();
      const todayUTC = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
      const filed = new Date(c.date_filed);
      const filedUTC = Date.UTC(filed.getUTCFullYear(), filed.getUTCMonth(), filed.getUTCDate());
      const daysAgo = (todayUTC - filedUTC) / (1000 * 60 * 60 * 24);
      if (daysAgo > Math.max(...f.days)) return false;
    }

    if (f.amounts.length > 0) {
      const amt = c.amount_raised;
      const BUCKET_UPPER: Record<number, number | null> = {
        0: 1_000_000,
        1_000_000: 10_000_000,
        10_000_000: 100_000_000,
        100_000_000: 500_000_000,
        500_000_000: null,
      };
      const passes = f.amounts.some(lo => {
        const hi = BUCKET_UPPER[lo];
        if (lo === 0) return amt === null || amt < 1_000_000;
        if (hi === null) return amt !== null && amt >= lo;
        return amt !== null && amt >= lo && amt < hi;
      });
      if (!passes) return false;
    }

    if (f.verticals.length > 0 && !matchesVertical(c.tags, f.verticals)) return false;

    if (f.rounds.length > 0 && !f.rounds.includes(normalizeRoundType(c.round_type))) return false;

    return true;
  });
}

function applyHiringFilters(companies: Company[], accelerators: string[], roleTypes: string[], roleLevels: string[], verticals: string[]): Company[] {
  return companies.filter((c) => {
    if (accelerators.length > 0) {
      const accels = c.accelerators ?? [c.accelerator];
      if (!accels.some(a => accelerators.includes(a))) return false;
    }
    if (verticals.length > 0 && !matchesVertical(c.tags, verticals)) return false;
    if (roleTypes.length > 0) {
      const hasType = roleTypes.some((r) => {
        if (r === "eng") return c.eng_count > 0;
        if (r === "product") return c.product_count > 0;
        if (r === "gtm") return c.gtm_count > 0;
        if (r === "other") return c.other_count > 0;
        return false;
      });
      if (!hasType) return false;
    }
    if (roleLevels.length > 0) {
      const hasLevel = roleLevels.some((r) => {
        if (r === "intern") return c.intern_count > 0;
        if (r === "new_grad") return c.new_grad_count > 0;
        if (r === "experienced") return (c.eng_count + c.product_count + c.gtm_count + c.other_count) > 0;
        return false;
      });
      if (!hasLevel) return false;
    }
    return true;
  });
}

function byDateDesc(a: Company, b: Company) {
  const ta = a.date_filed ? new Date(a.date_filed).getTime() : 0;
  const tb = b.date_filed ? new Date(b.date_filed).getTime() : 0;
  return tb - ta;
}

function byHiringDate(a: Company, b: Company) {
  const ta = a.date_filed ? new Date(a.date_filed).getTime() : 0;
  const tb = b.date_filed ? new Date(b.date_filed).getTime() : 0;
  if (tb !== ta) return tb - ta;
  const aPosted = a.date_source === "posted";
  const bPosted = b.date_source === "posted";
  return aPosted === bPosted ? 0 : aPosted ? -1 : 1;
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
  return (
    <div className="flex items-center justify-center gap-3 mt-8">
      <button
        onClick={() => onPage(Math.max(1, page - 1))}
        disabled={page === 1}
        className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronLeft size={18} />
      </button>
      <span className="text-sm text-muted-foreground tabular-nums">
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onPage(Math.min(totalPages, page + 1))}
        disabled={page === totalPages}
        className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronRight size={18} />
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


const visible = applyFilters(companies, filters);

  const recent = visible.sort(byDateDesc);

  const raisedTotalPages = Math.ceil(recent.length / PAGE_SIZE);
  const pagedRecent = recent.slice((raisedPage - 1) * PAGE_SIZE, raisedPage * PAGE_SIZE);

  const filteredHiring = applyHiringFilters(hiringCompanies, hiringAccelerators, hiringRoleTypes, hiringRoleLevels, hiringVerticals).sort(byHiringDate);
  const hiringTotalPages = Math.ceil(filteredHiring.length / PAGE_SIZE);
  const pagedHiring = filteredHiring.slice((hiringPage - 1) * PAGE_SIZE, hiringPage * PAGE_SIZE);

  const savedCompanies = companies
    .filter((c) => isBookmarked(c.id))
    .sort(byDateDesc);

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
          {/* Tab switcher */}
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
