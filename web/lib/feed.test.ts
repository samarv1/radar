import { describe, expect, it } from "vitest";
import type { Company } from "./db";
import {
  applyFilters,
  applyHiringFilters,
  dateSourceLabel,
  DEFAULT_FILTERS,
  formatDate,
  getVerticals,
  hiringStatus,
  normalizeRoundType,
  tagMatchesKeyword,
} from "./feed";

function company(overrides: Partial<Company> = {}): Company {
  return {
    id: 1,
    name: "Acme",
    website: "https://acme.test",
    accelerator: "yc",
    accelerators: ["yc"],
    batch: "W26",
    careers_url: "https://acme.test/jobs",
    amount_raised: 2_000_000,
    round_type: "Seed",
    date_filed: "2026-09-01",
    date_source: "raised",
    has_edgar: true,
    role_counts_authoritative: true,
    eng_count: 1,
    product_count: 0,
    gtm_count: 0,
    other_count: 0,
    intern_count: 1,
    new_grad_count: 0,
    experienced_count: 0,
    role_facets: ["engineering:intern"],
    tags: ["Artificial Intelligence"],
    location_tag: "bay_area",
    ...overrides,
  };
}

describe("feed filters", () => {
  it("uses UTC calendar days at the selected cutoff", () => {
    const result = applyFilters(
      [company({ date_filed: "2026-08-16" })],
      { ...DEFAULT_FILTERS, days: [30] },
      new Date("2026-09-15T23:59:59Z"),
    );
    expect(result).toHaveLength(1);
  });

  it("treats standalone role counts as unknown", () => {
    const standalone = company({ role_counts_authoritative: false, eng_count: 0, role_facets: [] });
    expect(hiringStatus(standalone)).toBe("unknown");
    expect(applyFilters([standalone], { ...DEFAULT_FILTERS, hiring: ["no"] })).toEqual([]);
  });

  it("matches role type and level on the same job", () => {
    const splitMatch = company({
      role_facets: ["engineering:experienced", "product:intern"],
      intern_count: 1,
      experienced_count: 1,
    });
    expect(applyHiringFilters([splitMatch], [], ["eng"], ["intern"], [])).toEqual([]);
    expect(applyHiringFilters([splitMatch], [], ["product"], ["intern"], [])).toEqual([splitMatch]);
  });
});

describe("feed presentation helpers", () => {
  it("normalizes round labels", () => {
    expect(normalizeRoundType("Series F")).toBe("series_e");
    expect(normalizeRoundType("Pre-Seed")).toBe("seed");
  });

  it("matches vertical prefixes without matching infixes", () => {
    expect(tagMatchesKeyword("Healthcare", "health")).toBe(true);
    expect(tagMatchesKeyword("Biomedical", "media")).toBe(false);
    expect(getVerticals(["Generative AI"])).toContain("ai");
  });

  it("formats filing-only dates in UTC", () => {
    expect(formatDate("2026-09-15", "raised")).toBe("Sep 15");
  });

  it("derives source labels from feed state", () => {
    expect(dateSourceLabel(company(), false, true)).toBe("raised");
    expect(dateSourceLabel(company({ has_edgar: false, date_source: "posted" }), true, false)).toBe("posted");
  });
});
