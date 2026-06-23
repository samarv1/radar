import { Flame, Bookmark } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import type { Company } from "@/lib/db";

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

function isRecent(date_filed: string): boolean {
  return Date.now() - new Date(date_filed).getTime() < THIRTY_DAYS_MS;
}

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
  if (company.amount_raised === null) {
    if (!company.careers_url) return null;
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
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                {SOURCE_LABELS[company.accelerator] ?? "None / Unknown"}
              </span>
              {!hideBatch && company.batch && (
                <span className="text-xs text-muted-foreground">{company.batch}</span>
              )}
            </div>
            <OpenRoles company={company} />
          </div>

          <div className="text-right shrink-0">
            {amount && (
              <p className="text-lg font-bold leading-none">{amount}</p>
            )}
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center justify-end gap-1">
              {fresh && (company.amount_raised !== null || company.date_source === "posted") && <Flame className="relative z-10 shrink-0 text-orange-400" size={13} />}
              <span>
                {amount
                  ? (company.has_edgar ? "raised " : "announced ")
                  : (company.date_source === "posted" ? "last posted " : "last checked ")}
                {formatDate(company.date_filed)}
              </span>
            </p>
          </div>
        </div>

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
      </CardHeader>
    </Card>
  );
}
