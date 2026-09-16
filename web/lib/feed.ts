import type { Company, DateSource } from "@/lib/db";

export type Filters = {
  accelerators: string[];
  hiring: string[];
  days: number[];
  amounts: number[];
  verticals: string[];
  rounds: string[];
  locations: string[];
};

export const DEFAULT_FILTERS: Filters = {
  accelerators: [],
  hiring: [],
  days: [],
  amounts: [],
  verticals: [],
  rounds: [],
  locations: [],
};

export const VERTICAL_KEYWORDS: Record<string, string[]> = {
  ai: ["ai", "artificial intelligence", "machine learning", "generative ai", "llm", "deep learning", "nlp", "computer vision"],
  fintech: ["fintech", "payments", "crypto", "blockchain", "banking", "insurtech", "lending", "wealth"],
  health: ["health", "biotech", "pharma", "medical", "clinical", "genomics", "drug", "therapy", "mental health"],
  b2b: ["saas", "b2b", "enterprise"],
  devtools: ["developer tools", "developer tool", "infrastructure", "open source", "devops", "security", "observability", "api", "platform engineering"],
  climate: ["climate", "cleantech", "sustainability", "energy", "carbon", "renewable"],
  consumer: ["consumer", "e-commerce", "marketplace", "gaming", "social", "entertainment", "media", "retail"],
  edtech: ["education", "edtech", "upskilling"],
  hardware: ["hardware", "robotics", "iot", "internet of things", "manufacturing", "semiconductors", "aerospace"],
};

const VERTICAL_PATTERNS = Object.fromEntries(
  Object.entries(VERTICAL_KEYWORDS).map(([vertical, keywords]) => [
    vertical,
    keywords.map((keyword) => new RegExp(`(?:^|\\W)${keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`)),
  ]),
);
const KEYWORD_PATTERNS = new Map(
  Object.entries(VERTICAL_KEYWORDS).flatMap(([vertical, keywords]) =>
    keywords.map((keyword, index) => [keyword, VERTICAL_PATTERNS[vertical][index]] as const),
  ),
);

const KNOWN_ACCELERATORS = new Set(["yc", "a16z", "sequoia", "pear", "lightspeed", "techstars"]);
const AMOUNT_BUCKETS = new Map<number, number | null>([
  [0, 1_000_000],
  [1_000_000, 10_000_000],
  [10_000_000, 100_000_000],
  [100_000_000, 500_000_000],
  [500_000_000, null],
]);
const DAY_MS = 24 * 60 * 60 * 1000;

export function tagMatchesKeyword(tag: string, keyword: string): boolean {
  return KEYWORD_PATTERNS.get(keyword)?.test(tag.toLowerCase()) ?? false;
}

export function getVerticals(tags: string[] | null): string[] {
  if (!tags?.length) return [];
  return Object.entries(VERTICAL_PATTERNS)
    .filter(([, patterns]) => patterns.some((pattern) => tags.some((tag) => pattern.test(tag.toLowerCase()))))
    .map(([vertical]) => vertical)
    .slice(0, 3);
}

export function matchesVertical(tags: string[] | null, verticals: string[]): boolean {
  if (!tags?.length) return verticals.includes("unknown");
  return verticals.some(
    (vertical) => vertical !== "unknown" && VERTICAL_PATTERNS[vertical]?.some(
      (pattern) => tags.some((tag) => pattern.test(tag.toLowerCase())),
    ),
  );
}

export function normalizeRoundType(roundType: string | null): string {
  if (!roundType) return "unknown";
  const normalized = roundType.toLowerCase().trim();
  if (normalized.includes("pre") || normalized === "seed") return "seed";
  if (normalized.includes("series a")) return "series_a";
  if (normalized.includes("series b")) return "series_b";
  if (normalized.includes("series c")) return "series_c";
  if (normalized.includes("series d")) return "series_d";
  if (/series [efg]/.test(normalized)) return "series_e";
  return "unknown";
}

export function hiringStatus(company: Company): "yes" | "no" | "unknown" {
  if (!company.role_counts_authoritative) return "unknown";
  return totalRoles(company) > 0 ? "yes" : "no";
}

export function totalRoles(company: Company): number {
  return company.eng_count + company.product_count + company.gtm_count + company.other_count;
}

export function applyFilters(companies: Company[], filters: Filters, now = new Date()): Company[] {
  return companies.filter((company) => {
    if (filters.accelerators.length) {
      const accelerators = company.accelerators ?? [company.accelerator];
      const matchesKnown = accelerators.some((accelerator) => filters.accelerators.includes(accelerator));
      const matchesUnknown = filters.accelerators.includes("unknown")
        && !accelerators.some((accelerator) => KNOWN_ACCELERATORS.has(accelerator));
      if (!matchesKnown && !matchesUnknown) return false;
    }
    if (filters.hiring.length && !filters.hiring.includes(hiringStatus(company))) return false;
    if (filters.days.length) {
      const todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
      const filed = new Date(company.date_filed);
      const filedUtc = Date.UTC(filed.getUTCFullYear(), filed.getUTCMonth(), filed.getUTCDate());
      if ((todayUtc - filedUtc) / DAY_MS > Math.max(...filters.days)) return false;
    }
    if (filters.amounts.length) {
      const passes = filters.amounts.some((lower) => {
        const upper = AMOUNT_BUCKETS.get(lower);
        if (lower === 0) return company.amount_raised === null || company.amount_raised < 1_000_000;
        if (upper === null) return company.amount_raised !== null && company.amount_raised >= lower;
        return upper !== undefined && company.amount_raised !== null
          && company.amount_raised >= lower && company.amount_raised < upper;
      });
      if (!passes) return false;
    }
    if (filters.verticals.length && !matchesVertical(company.tags, filters.verticals)) return false;
    if (filters.rounds.length && !filters.rounds.includes(normalizeRoundType(company.round_type))) return false;
    return !filters.locations.length || filters.locations.includes(company.location_tag ?? "unknown");
  });
}

export function applyHiringFilters(
  companies: Company[],
  accelerators: string[],
  roleTypes: string[],
  roleLevels: string[],
  verticals: string[],
): Company[] {
  return companies.filter((company) => {
    const companyAccelerators = company.accelerators ?? [company.accelerator];
    if (accelerators.length && !companyAccelerators.some((accelerator) => accelerators.includes(accelerator))) return false;
    if (verticals.length && !matchesVertical(company.tags, verticals)) return false;

    const selectedTypes = roleTypes.map((role) => role === "eng" ? "engineering" : role);
    if (selectedTypes.length && roleLevels.length) {
      return company.role_facets.some((facet) => {
        const [type, level] = facet.split(":");
        return selectedTypes.includes(type) && roleLevels.includes(level);
      });
    }
    if (selectedTypes.length && !selectedTypes.some((type) => roleTypeCount(company, type) > 0)) return false;
    if (roleLevels.length && !roleLevels.some((level) => roleLevelCount(company, level) > 0)) return false;
    return true;
  });
}

function roleTypeCount(company: Company, roleType: string): number {
  if (roleType === "engineering") return company.eng_count;
  if (roleType === "product") return company.product_count;
  if (roleType === "gtm") return company.gtm_count;
  return roleType === "other" ? company.other_count : 0;
}

function roleLevelCount(company: Company, roleLevel: string): number {
  if (roleLevel === "intern") return company.intern_count;
  if (roleLevel === "new_grad") return company.new_grad_count;
  return roleLevel === "experienced" ? company.experienced_count : 0;
}

export function byDateDesc(a: Company, b: Company): number {
  return new Date(b.date_filed).getTime() - new Date(a.date_filed).getTime();
}

export function byHiringDate(a: Company, b: Company): number {
  const difference = byDateDesc(a, b);
  if (difference) return difference;
  if (a.date_source === b.date_source) return 0;
  return a.date_source === "posted" ? -1 : 1;
}

export function formatAmount(amount: number | null): string | null {
  if (amount === null || amount < 10_000) return null;
  if (amount >= 1_000_000_000) return `$${(amount / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}B`;
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(0)}M`;
  return `$${(amount / 1_000).toFixed(0)}K`;
}

export function formatDate(date: string, dateSource: DateSource): string {
  const options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  // Filing dates have no time component, so UTC avoids a one-day shift.
  if (dateSource === "raised") options.timeZone = "UTC";
  return new Date(date).toLocaleDateString("en-US", options);
}

export function isRecent(date: string, now = Date.now()): boolean {
  return now - new Date(date).getTime() < 30 * DAY_MS;
}

export function dateSourceLabel(company: Company, hiringMode: boolean, hasAmount: boolean): string {
  if (hiringMode) return company.date_source === "posted" ? "posted" : "discovered";
  if (company.has_edgar) return "raised";
  if (company.date_source === "announced" || (hasAmount && !company.has_edgar)) return "announced";
  return company.date_source === "posted" ? "posted" : "discovered";
}
