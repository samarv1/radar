import { Badge } from "@/components/ui/badge";
import type { Company } from "@/lib/db";

const CATEGORY_STYLES: Record<string, string> = {
  eng:     "bg-blue-100 text-blue-800 hover:bg-blue-100",
  gtm:     "bg-green-100 text-green-800 hover:bg-green-100",
  product: "bg-purple-100 text-purple-800 hover:bg-purple-100",
  other:   "bg-gray-100 text-gray-700 hover:bg-gray-100",
};

const LABELS: Record<string, string> = {
  eng: "eng", gtm: "gtm", product: "product", other: "other",
};

type Props = Pick<Company, "careers_ats" | "eng_count" | "product_count" | "gtm_count" | "other_count">;

export function HiringTags({ careers_ats, eng_count, product_count, gtm_count, other_count }: Props) {
  const hasData = careers_ats && careers_ats !== "not_found";

  if (!hasData) {
    return <p className="text-xs text-muted-foreground italic">hiring data unavailable</p>;
  }

  const counts: [string, number][] = [
    ["eng", eng_count],
    ["gtm", gtm_count],
    ["product", product_count],
    ["other", other_count],
  ].filter(([, n]) => (n as number) > 0) as [string, number][];

  if (counts.length === 0) {
    return <p className="text-xs text-muted-foreground italic">no open roles</p>;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {counts.map(([cat, n]) => (
        <Badge key={cat} className={`text-xs font-medium ${CATEGORY_STYLES[cat]}`}>
          {n} {LABELS[cat]}
        </Badge>
      ))}
    </div>
  );
}
