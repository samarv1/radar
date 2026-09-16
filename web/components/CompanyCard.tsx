"use client";

import { Flame, Bookmark } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import type { Company } from "@/lib/db";
import { dateSourceLabel, formatAmount, formatDate, getVerticals, isRecent, totalRoles } from "@/lib/feed";

const VERTICAL_LABELS: Record<string, string> = {
  ai: "AI / ML",
  fintech: "Fintech",
  health: "Health",
  b2b: "B2B / SaaS",
  devtools: "Dev Tools",
  climate: "Climate",
  consumer: "Consumer",
  edtech: "EdTech",
  hardware: "Hardware",
};

const SOURCE_LABELS: Record<string, string> = {
  yc: "YC",
  a16z: "a16z",
  sequoia: "Sequoia",
  pear: "Pear",
  lightspeed: "Lightspeed",
  techstars: "Techstars",
};

const LOCATION_LABELS: Record<string, string> = {
  bay_area: "Bay Area",
  new_york: "New York",
  other_usa: "Other USA",
  international: "International",
};

function OpenRoles({ company, hiringMode }: { company: Company; hiringMode: boolean }) {
  if (!hiringMode && company.amount_raised === null && company.careers_url) {
    return (
      <div className="flex items-baseline gap-1.5 text-xs text-muted-foreground pt-1">
        <span className="shrink-0">Open roles</span>
        <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="relative z-10 hover:opacity-70 transition-opacity font-medium text-green-600">
          apply ↗
        </a>
      </div>
    );
  }

  let status: React.ReactNode;
  if (!company.role_counts_authoritative) {
    status = company.careers_url ? (
      <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="relative z-10 hover:opacity-70 transition-opacity font-medium text-green-600">
        apply ↗
      </a>
    ) : <span className="text-muted-foreground/50">—</span>;
  } else if (totalRoles(company) === 0) {
    status = <span className="text-muted-foreground/50">none</span>;
  } else {
    status = company.careers_url ? (
      <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="relative z-10 hover:opacity-70 transition-opacity font-medium text-green-600">
        yes ↗
      </a>
    ) : <span className="font-medium text-green-600">yes</span>;
  }

  return (
    <div className="flex items-baseline gap-1.5 text-xs text-muted-foreground pt-1">
      <span className="shrink-0">Open roles</span>
      {status}
    </div>
  );
}

export function CompanyCard({
  company,
  isBookmarked,
  onToggleBookmark,
  hideBatch = false,
  hiringMode = false,
}: {
  company: Company;
  isBookmarked: boolean;
  onToggleBookmark: () => void;
  hideBatch?: boolean;
  hiringMode?: boolean;
}) {
  const amount = hiringMode ? null : formatAmount(company.amount_raised);
  const fresh = isRecent(company.date_filed);
  const verticals = getVerticals(company.tags);
  const roundLabel = hiringMode ? null : (company.round_type ?? null);
  const accelBadges = (company.accelerators ?? [company.accelerator]).filter(a => SOURCE_LABELS[a]);
  const locationLabel = company.location_tag ? LOCATION_LABELS[company.location_tag] : null;
  const showAccelRow = accelBadges.length > 0 || (!hideBatch && !!company.batch);

  return (
    <Card className={`relative transition-shadow ${company.website ? "hover:shadow-md" : ""}`}>
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-0.5">
            <p className="text-base font-semibold leading-tight">
              {company.website ? (
                <a
                  href={company.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="after:absolute after:inset-0"
                >
                  {company.name}
                </a>
              ) : company.name}
            </p>
            {/* Reserve the tallest row stack so cards stay aligned when metadata is absent. */}
            <div className="min-h-[84px]">
              {showAccelRow && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  {accelBadges.map((a) => (
                    <span key={a} className="text-xs font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                      {SOURCE_LABELS[a]}
                    </span>
                  ))}
                  {!hideBatch && company.batch && (
                    <span className="text-xs text-muted-foreground">{company.batch}</span>
                  )}
                </div>
              )}
              {verticals.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {verticals.map((v) => (
                    <span key={v} className="text-xs text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950/50 px-1.5 py-0.5 rounded">
                      {VERTICAL_LABELS[v]}
                    </span>
                  ))}
                </div>
              )}
              {locationLabel && (
                <div className="flex flex-wrap gap-1 pt-1">
                  <span className="text-xs text-rose-500 bg-rose-50/60 dark:text-rose-300 dark:bg-rose-950/30 px-1.5 py-0.5 rounded">
                    {locationLabel}
                  </span>
                </div>
              )}
              <OpenRoles company={company} hiringMode={hiringMode} />
            </div>
          </div>

          <div className="text-right shrink-0">
            {amount && <p className="text-lg font-bold leading-none">{amount}</p>}
            {roundLabel && (
              <p className="text-xs text-muted-foreground/70">{roundLabel}</p>
            )}
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center justify-end gap-1">
              {fresh && (company.has_edgar || company.date_source === "announced" || company.date_source === "posted" || company.date_source === "discovered") && <Flame className="relative z-10 shrink-0 text-orange-400" size={13} />}
              <span>
                {dateSourceLabel(company, hiringMode, amount !== null)}{" "}
                {formatDate(company.date_filed, company.date_source)}
              </span>
            </p>
          </div>
        </div>
      </CardHeader>

      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggleBookmark();
        }}
        title={isBookmarked ? "Remove bookmark" : "Save company"}
        className="absolute bottom-3 right-3 z-10 p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
      >
        <Bookmark
          size={14}
          fill={isBookmarked ? "currentColor" : "none"}
        />
      </button>
    </Card>
  );
}
