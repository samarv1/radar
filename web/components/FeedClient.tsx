"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import { Radar, Bookmark, ChevronLeft, ChevronRight } from "lucide-react";
import { FilterBar, HiringFilterBar, DEFAULT_FILTERS, VERTICAL_KEYWORDS, tagMatchesKeyword, normalizeRoundType, type Filters } from "@/components/FilterBar";
import { CompanyCard } from "@/components/CompanyCard";
import { useBookmarks } from "@/lib/useBookmarks";
import type { Company } from "@/lib/db";

const PAGE_SIZE = 15;

const SIX_MONTHS_MS = 180 * 24 * 60 * 60 * 1000;

function hiringStatus(c: Company): "yes" | "no" | "unknown" {
  // not_found + valid website = we checked their site and found no careers page
  if (c.careers_ats === "not_found" && c.website) return "no";
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
      const isKnown = KNOWN_ACCELERATORS.includes(c.accelerator);
      const matchesAccel = f.accelerators.includes(c.accelerator);
      const matchesUnknown = f.accelerators.includes("unknown") && !isKnown;
      if (!matchesAccel && !matchesUnknown) return false;
    }

    if (f.hiring.length > 0 && !f.hiring.includes(hiringStatus(c))) return false;

    if (f.days.length > 0) {
      const daysAgo = (Date.now() - new Date(c.date_filed).getTime()) / (1000 * 60 * 60 * 24);
      if (daysAgo > Math.max(...f.days)) return false;
    }

    if (f.amounts.length > 0) {
      if (c.amount_raised === null || c.amount_raised > Math.max(...f.amounts)) return false;
    }

    if (f.verticals.length > 0 && !matchesVertical(c.tags, f.verticals)) return false;

    if (f.rounds.length > 0 && !f.rounds.includes(normalizeRoundType(c.round_type))) return false;

    return true;
  });
}

function applyHiringFilters(companies: Company[], accelerators: string[], roleTypes: string[], roleLevels: string[], verticals: string[]): Company[] {
  return companies.filter((c) => {
    if (accelerators.length > 0 && !accelerators.includes(c.accelerator)) return false;
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
  const aPosted = a.date_source === "posted";
  const bPosted = b.date_source === "posted";
  if (aPosted !== bPosted) return aPosted ? -1 : 1;
  const ta = a.date_filed ? new Date(a.date_filed).getTime() : 0;
  const tb = b.date_filed ? new Date(b.date_filed).getTime() : 0;
  return tb - ta;
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
  const [expandedOld, setExpandedOld] = useState(false);
  const [tab, setTab] = useState<"raised" | "hiring">("hiring");
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

  function handleHiringAccelChange(v: string[]) {
    setHiringAccelerators(v);
    setHiringPage(1);
  }

  function handleHiringRoleTypesChange(v: string[]) {
    setHiringRoleTypes(v);
    setHiringPage(1);
  }

  function handleHiringRoleLevelsChange(v: string[]) {
    setHiringRoleLevels(v);
    setHiringPage(1);
  }

  function handleHiringVerticalsChange(v: string[]) {
    setHiringVerticals(v);
    setHiringPage(1);
  }

const visible = applyFilters(companies, filters);
  // eslint-disable-next-line react-hooks/purity
  const now = useMemo(() => Date.now(), []);

  const recent = visible
    .filter((c) => now - new Date(c.date_filed).getTime() < SIX_MONTHS_MS)
    .sort(byDateDesc);

  const oldCompanies = visible
    .filter((c) => now - new Date(c.date_filed).getTime() >= SIX_MONTHS_MS)
    .sort(byDateDesc);

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
                          <CompanyCard
                            key={c.id}
                            company={c}
                            isBookmarked={isBookmarked(c.id)}
                            onToggleBookmark={() => toggle(c.id)}
                          />
                        ))}
                      </div>
                    )}
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
                onAccelerators={handleHiringAccelChange}
                onRoleTypes={handleHiringRoleTypesChange}
                onRoleLevels={handleHiringRoleLevelsChange}
                onVerticals={handleHiringVerticalsChange}
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
