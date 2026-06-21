import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { HiringTags } from "@/components/HiringTags";
import type { Company } from "@/lib/db";

const ACC_LABELS: Record<string, string> = {
  yc: "YC", a16z: "a16z", sequoia: "SEQ",
  pear: "PEAR", lightspeed: "LS", techstars: "TS",
};

function formatAmount(n: number | null): string {
  if (n === null) return "undisclosed";
  if (n === 0) return "undisclosed";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n}`;
}

function formatDate(s: string): string {
  return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatWebsite(url: string | null): string | null {
  if (!url) return null;
  return url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
}

export function CompanyCard({ company }: { company: Company }) {
  const href = company.website ?? "#";

  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="block group">
      <Card className="h-full transition-shadow group-hover:shadow-md">
        <CardHeader className="pb-2 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <span className="text-base font-semibold leading-tight group-hover:underline">
              {company.name}
            </span>
            <div className="flex gap-1 shrink-0">
              <Badge variant="outline" className="text-xs">
                {ACC_LABELS[company.accelerator] ?? company.accelerator.toUpperCase()}
              </Badge>
              {company.batch && (
                <Badge variant="secondary" className="text-xs">
                  {company.batch}
                </Badge>
              )}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {formatWebsite(company.website) ?? "—"}
            {" · "}
            {formatAmount(company.amount_raised)}
            {" · "}
            {formatDate(company.date_filed)}
          </p>
        </CardHeader>
        <Separator />
        <CardContent className="pt-3 pb-3">
          <HiringTags
            careers_ats={company.careers_ats}
            eng_count={company.eng_count}
            product_count={company.product_count}
            gtm_count={company.gtm_count}
            other_count={company.other_count}
          />
        </CardContent>
      </Card>
    </a>
  );
}
