import { Flame } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import type { Company } from "@/lib/db";

const ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000;

function isNew(created_at: string): boolean {
  return Date.now() - new Date(created_at).getTime() < ONE_WEEK_MS;
}

const ROLE_COLORS: Record<string, string> = {
  eng:     "text-blue-600",
  gtm:     "text-green-600",
  product: "text-purple-600",
  other:   "text-gray-500",
};

function formatAmount(n: number | null): string | null {
  if (n === null || n < 10_000) return null;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return null;
}

function formatDate(s: string): string {
  return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function OpenRoles({ company }: { company: Company }) {
  const hasData = company.careers_ats && company.careers_ats !== "not_found";

  if (!hasData) {
    return <span className="text-muted-foreground italic">no data</span>;
  }

  const counts: [string, number][] = [
    ["eng",     company.eng_count],
    ["gtm",     company.gtm_count],
    ["product", company.product_count],
    ["other",   company.other_count],
  ].filter(([, n]) => (n as number) > 0) as [string, number][];

  if (counts.length === 0) {
    return <span className="text-muted-foreground italic">none currently</span>;
  }

  const content = (
    <span className="text-xs">
      {counts.map(([cat, n], i) => (
        <span key={cat}>
          <span className={`font-medium ${ROLE_COLORS[cat]}`}>{n} {cat}</span>
          {i < counts.length - 1 && <span className="text-muted-foreground"> · </span>}
        </span>
      ))}
      {company.careers_url && (
        <span className="text-muted-foreground ml-1">↗</span>
      )}
    </span>
  );

  return company.careers_url ? (
    <a
      href={company.careers_url}
      target="_blank"
      rel="noopener noreferrer"
      className="relative z-10 hover:opacity-70 transition-opacity"
    >
      {content}
    </a>
  ) : content;
}

export function CompanyCard({ company }: { company: Company }) {
  const amount = formatAmount(company.amount_raised);
  const fresh = isNew(company.created_at);

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
            {company.batch && (
              <p className="text-xs text-muted-foreground">{company.batch}</p>
            )}
            <p className="text-xs text-muted-foreground pt-1">
              <span className="mr-1.5">Open roles:</span>
              <OpenRoles company={company} />
            </p>
          </div>

          <div className="text-right shrink-0">
            {amount && (
              <p className="text-lg font-bold leading-none">{amount}</p>
            )}
            <p className="text-xs text-muted-foreground mt-0.5">
              {amount ? "raised " : ""}{formatDate(company.date_filed)}
            </p>
          </div>
        </div>
      </CardHeader>
    </Card>
  );
}
