"use client";

import { Flame, Bookmark } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { getRoundFromAmount, VERTICAL_KEYWORDS, tagMatchesKeyword } from "@/components/FilterBar";
import type { Company } from "@/lib/db";

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;


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

function getVerticals(tags: string[] | null): string[] {
  if (!tags || tags.length === 0) return [];
  return Object.entries(VERTICAL_KEYWORDS)
    .filter(([, keywords]) =>
      keywords.some((kw) => tags.some((t) => tagMatchesKeyword(t, kw)))
    )
    .map(([key]) => key)
    .slice(0, 3);
}

function isRecent(date_filed: string): boolean {
  return Date.now() - new Date(date_filed).getTime() < THIRTY_DAYS_MS;
}

const ROUND_LABELS: Record<string, string> = {
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C+",
};

const SOURCE_LABELS: Record<string, string> = {
  yc: "YC",
  a16z: "a16z",
  sequoia: "Sequoia",
  pear: "Pear",
  lightspeed: "Lightspeed",
  techstars: "Techstars",
};

function formatAmount(n: number | null): string | null {
  if (n === null || n < 10_000) return null;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return null;
}

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function OpenRoles({ company }: { company: Company }) {
  if (company.amount_raised === null && company.careers_url) {
    return (
      <div className="flex items-baseline gap-1.5 text-xs text-muted-foreground pt-1">
        <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="relative z-10 hover:opacity-70 transition-opacity font-medium text-green-600">
          apply ↗
        </a>
      </div>
    );
  }

  const hasData = company.careers_ats && company.careers_ats !== "not_found";
  const total = company.eng_count + company.gtm_count + company.product_count + company.other_count;

  let status: React.ReactNode;
  if (!hasData) {
    status = <span className="text-muted-foreground/50">—</span>;
  } else if (total === 0) {
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
}: {
  company: Company;
  isBookmarked: boolean;
  onToggleBookmark: () => void;
  hideBatch?: boolean;
}) {
  const amount = formatAmount(company.amount_raised);
  const fresh = isRecent(company.date_filed);
  const verticals = getVerticals(company.tags);
  const roundLabel = ROUND_LABELS[getRoundFromAmount(company.amount_raised)] ?? null;
  const hasAccel = SOURCE_LABELS[company.accelerator] !== undefined;
  const showAccelRow = hasAccel || (!hideBatch && !!company.batch);
  // Each variable row contributes (2px space-y margin + height)px to the left column.
  // accel row: 22px, chips row: 26px, openRoles row: always 22px. Target = 70px.
  // Spacer itself gets 2px margin-top, so spacerH = target - present rows - 2.
  const spacerH = Math.max(0, 70 - (showAccelRow ? 22 : 0) - (verticals.length > 0 ? 26 : 0) - 22 - 2);

  return (
    <Card className={`relative transition-shadow ${company.website ? "hover:shadow-md" : ""}`}>
      <CardHeader className="pb-8">
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
            {showAccelRow && (
              <div className="flex items-center gap-1.5 flex-wrap">
                {hasAccel && (
                  <span className="text-xs font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                    {SOURCE_LABELS[company.accelerator]}
                  </span>
                )}
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
            <OpenRoles company={company} />
            {spacerH > 0 && <div style={{ height: spacerH }} />}
          </div>

          <div className="text-right shrink-0">
            {amount && <p className="text-lg font-bold leading-none">{amount}</p>}
            {roundLabel && (
              <p className="text-xs text-muted-foreground/70">{roundLabel}</p>
            )}
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center justify-end gap-1">
              {fresh && (company.has_edgar || company.date_source === "announced" || company.date_source === "posted") && <Flame className="relative z-10 shrink-0 text-orange-400" size={13} />}
              <span>
                {company.has_edgar
                  ? "raised "
                  : (company.date_source === "announced" || (amount !== null && !company.has_edgar))
                    ? "announced "
                    : company.date_source === "posted"
                      ? "last posted "
                      : "last checked "}
                {formatDate(company.date_filed)}
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
