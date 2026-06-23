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

function formatDate(s: string): string {
  return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function HiringStatus({ company }: { company: Company }) {
  const hasData = company.careers_ats && company.careers_ats !== "not_found";

  if (!hasData) {
    return <span className="text-muted-foreground italic">unknown</span>;
  }

  const total = company.eng_count + company.gtm_count + company.product_count + company.other_count;

  if (total === 0) {
    return <span className="text-muted-foreground italic">no</span>;
  }

  const label = (
    <span className="font-medium text-green-600">
      yes{company.careers_url && <span className="text-muted-foreground font-normal ml-0.5">↗</span>}
    </span>
  );

  return company.careers_url ? (
    <a
      href={company.careers_url}
      target="_blank"
      rel="noopener noreferrer"
      className="relative z-10 hover:opacity-70 transition-opacity"
    >
      {label}
    </a>
  ) : label;
}

export function CompanyCard({
  company,
  isBookmarked,
  onToggleBookmark,
}: {
  company: Company;
  isBookmarked: boolean;
  onToggleBookmark: () => void;
}) {
  const amount = formatAmount(company.amount_raised);
  const fresh = isRecent(company.date_filed);

  return (
    <Card className={`relative transition-shadow ${company.website ? "hover:shadow-md" : ""}`}>
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-0.5">
            <p className="text-base font-semibold leading-tight flex items-center gap-1.5">
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
              {fresh && (
                <Flame className="relative z-10 shrink-0 text-orange-400" size={14} />
              )}
            </p>
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                {SOURCE_LABELS[company.accelerator] ?? "None / Unknown"}
              </span>
              {company.batch && (
                <span className="text-xs text-muted-foreground">{company.batch}</span>
              )}
            </div>
            <div className="flex items-baseline gap-1.5 text-xs text-muted-foreground pt-1">
              <span className="shrink-0">Actively hiring?</span>
              <HiringStatus company={company} />
            </div>
          </div>

          <div className="text-right shrink-0">
            {amount && (
              <p className="text-lg font-bold leading-none">{amount}</p>
            )}
            <p className="text-xs text-muted-foreground mt-0.5">
              {amount ? (company.has_edgar ? "raised " : "announced ") : ""}{formatDate(company.date_filed)}
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
