import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export type Company = {
  id: number;
  name: string;
  website: string | null;
  accelerator: string;
  batch: string | null;
  careers_ats: string | null;
  careers_url: string | null;
  amount_raised: number | null;
  date_filed: string;
  created_at: string;
  has_edgar: boolean;
  eng_count: number;
  product_count: number;
  gtm_count: number;
  other_count: number;
};

export type LastUpdated = { date: Date; type: "filing" | "announcement" };

export async function getLastUpdated(): Promise<LastUpdated | null> {
  const { rows } = await pool.query<{ signal_date: Date; signal_type: string }>(
    `SELECT signal_date, signal_type FROM (
       SELECT MAX(e.date_filed) AS signal_date, 'filing' AS signal_type
       FROM edgar_filings e
       LEFT JOIN accelerator_companies a ON e.accelerator_id = a.id
       WHERE (
         (e.accelerator_id IS NOT NULL AND a.is_excluded = FALSE)
         OR (e.accelerator_id IS NULL AND e.standalone_source IS NOT NULL)
       )
       AND (e.amount_raised IS NULL OR e.amount_raised <= 100000000)

       UNION ALL

       SELECT MAX(fn.published_at::date) AS signal_date, 'announcement' AS signal_type
       FROM funding_news fn
       WHERE fn.accelerator_id IS NULL
         AND fn.amount_usd IS NOT NULL AND fn.amount_usd <= 100000000
         AND array_length(regexp_split_to_array(trim(fn.company_name), '\\s+'), 1) <= 3
         AND fn.company_name NOT LIKE '%:%'
         AND fn.company_name NOT LIKE '%,%'
         AND fn.company_name !~* '\\y(capital|fund|venture|ventures|partner|partners|vc)\\y'
     ) combined
     ORDER BY signal_date DESC NULLS LAST
     LIMIT 1`
  );
  const row = rows[0];
  if (!row?.signal_date) return null;
  return { date: row.signal_date, type: row.signal_type as "filing" | "announcement" };
}

export async function getHiringFeed(): Promise<Company[]> {
  const { rows } = await pool.query<Company>(`
    SELECT DISTINCT ON (a.id)
      a.id, a.name, a.website, a.accelerator, a.batch,
      a.careers_ats, a.careers_url, a.created_at::text,
      NULL::float AS amount_raised,
      a.careers_scraped_at::date::text AS date_filed,
      FALSE AS has_edgar,
      COALESCE(h.eng, 0)::int     AS eng_count,
      COALESCE(h.product, 0)::int AS product_count,
      COALESCE(h.gtm, 0)::int     AS gtm_count,
      COALESCE(h.other, 0)::int   AS other_count
    FROM accelerator_companies a
    JOIN (
      SELECT company_id,
        SUM(CASE WHEN category = 'engineering' THEN 1 ELSE 0 END) AS eng,
        SUM(CASE WHEN category = 'product'     THEN 1 ELSE 0 END) AS product,
        SUM(CASE WHEN category = 'gtm'         THEN 1 ELSE 0 END) AS gtm,
        SUM(CASE WHEN category = 'other'       THEN 1 ELSE 0 END) AS other
      FROM job_listings GROUP BY company_id
    ) h ON h.company_id = a.id
    WHERE a.is_excluded = FALSE
      AND (h.eng + h.product + h.gtm + h.other) > 0
      -- Not already in the Raised feed (no EDGAR filing in last 90 days)
      AND NOT EXISTS (
        SELECT 1 FROM edgar_filings ef
        WHERE ef.accelerator_id = a.id
          AND ef.date_filed >= NOW() - INTERVAL '90 days'
      )
      -- Exclude companies with any known large raise
      AND NOT EXISTS (
        SELECT 1 FROM edgar_filings ef
        WHERE ef.accelerator_id = a.id
          AND ef.amount_raised > 100000000
      )
    ORDER BY a.id
  `);
  return rows;
}

export async function getFeed(): Promise<Company[]> {
  const { rows } = await pool.query<Company>(`
    SELECT * FROM (
      -- Accelerator-backed companies with EDGAR filings
      SELECT DISTINCT ON (a.id)
        a.id, a.name, a.website, a.accelerator, a.batch,
        a.careers_ats, a.careers_url, a.created_at::text,
        e.amount_raised::float AS amount_raised, e.date_filed::text,
        TRUE AS has_edgar,
        COALESCE(h.eng, 0)::int     AS eng_count,
        COALESCE(h.product, 0)::int AS product_count,
        COALESCE(h.gtm, 0)::int     AS gtm_count,
        COALESCE(h.other, 0)::int   AS other_count
      FROM accelerator_companies a
      JOIN edgar_filings e ON e.accelerator_id = a.id
      LEFT JOIN (
        SELECT company_id,
          SUM(CASE WHEN category = 'engineering' THEN 1 ELSE 0 END) AS eng,
          SUM(CASE WHEN category = 'product'     THEN 1 ELSE 0 END) AS product,
          SUM(CASE WHEN category = 'gtm'         THEN 1 ELSE 0 END) AS gtm,
          SUM(CASE WHEN category = 'other'       THEN 1 ELSE 0 END) AS other
        FROM job_listings GROUP BY company_id
      ) h ON h.company_id = a.id
      WHERE a.is_excluded = FALSE
        AND (e.amount_raised IS NULL OR e.amount_raised <= 100000000)
      ORDER BY a.id, e.date_filed DESC
    ) accel

    UNION ALL

    -- Non-accelerator EDGAR filings validated by TC/PH match or Other Technology industry group
    SELECT * FROM (
      SELECT DISTINCT ON (ef.company_name)
        -ef.id        AS id,
        ef.company_name AS name,
        NULL::text    AS website,
        ef.standalone_source AS accelerator,
        NULL::text    AS batch,
        NULL::text    AS careers_ats,
        NULL::text    AS careers_url,
        ef.created_at::text,
        ef.amount_raised::float AS amount_raised,
        ef.date_filed::text,
        TRUE AS has_edgar,
        0::int AS eng_count,
        0::int AS product_count,
        0::int AS gtm_count,
        0::int AS other_count
      FROM edgar_filings ef
      WHERE ef.accelerator_id IS NULL
        AND ef.standalone_source IS NOT NULL
        AND (ef.amount_raised IS NULL OR ef.amount_raised <= 100000000)
      ORDER BY ef.company_name, ef.date_filed DESC
    ) standalone

    UNION ALL

    -- TechCrunch-announced companies without a Form D filing yet.
    -- Quality filters: real funding amount, short name (not a descriptor fragment),
    -- no comma/colon in name (descriptor prefix pattern), no VC fund keywords.
    -- Excludes companies already in the standalone EDGAR path to avoid duplicates.
    SELECT * FROM (
      SELECT DISTINCT ON (fn.company_name)
        fn.id + 1000000 AS id,
        fn.company_name AS name,
        NULL::text      AS website,
        'techcrunch'::text AS accelerator,
        NULL::text      AS batch,
        NULL::text      AS careers_ats,
        NULL::text      AS careers_url,
        fn.created_at::text,
        fn.amount_usd::float AS amount_raised,
        fn.published_at::date::text AS date_filed,
        FALSE AS has_edgar,
        0::int AS eng_count,
        0::int AS product_count,
        0::int AS gtm_count,
        0::int AS other_count
      FROM funding_news fn
      WHERE fn.accelerator_id IS NULL
        AND fn.amount_usd IS NOT NULL
        AND fn.amount_usd <= 100000000
        AND array_length(regexp_split_to_array(trim(fn.company_name), '\s+'), 1) <= 3
        AND fn.company_name NOT LIKE '%:%'
        AND fn.company_name NOT LIKE '%,%'
        AND fn.company_name !~* '\y(capital|fund|venture|ventures|partner|partners|vc)\y'
        AND NOT EXISTS (
          SELECT 1 FROM edgar_filings ef2
          WHERE ef2.accelerator_id IS NULL
            AND ef2.standalone_source IS NOT NULL
            AND LOWER(TRIM(ef2.company_name)) = LOWER(TRIM(fn.company_name))
        )
      ORDER BY fn.company_name, fn.published_at DESC
    ) tc_only

    UNION ALL

    -- Accelerator-backed companies announced in TC but no Form D filed yet.
    -- Shows the real accelerator badge (YC, a16z, etc.) with "announced" label.
    -- Excluded once they file Form D (they'll appear in the first branch instead).
    SELECT * FROM (
      SELECT DISTINCT ON (a.id)
        a.id, a.name, a.website, a.accelerator, a.batch,
        a.careers_ats, a.careers_url, a.created_at::text,
        fn.amount_usd::float AS amount_raised,
        fn.published_at::date::text AS date_filed,
        FALSE AS has_edgar,
        COALESCE(h.eng, 0)::int     AS eng_count,
        COALESCE(h.product, 0)::int AS product_count,
        COALESCE(h.gtm, 0)::int     AS gtm_count,
        COALESCE(h.other, 0)::int   AS other_count
      FROM accelerator_companies a
      JOIN funding_news fn ON fn.accelerator_id = a.id
      LEFT JOIN (
        SELECT company_id,
          SUM(CASE WHEN category = 'engineering' THEN 1 ELSE 0 END) AS eng,
          SUM(CASE WHEN category = 'product'     THEN 1 ELSE 0 END) AS product,
          SUM(CASE WHEN category = 'gtm'         THEN 1 ELSE 0 END) AS gtm,
          SUM(CASE WHEN category = 'other'       THEN 1 ELSE 0 END) AS other
        FROM job_listings GROUP BY company_id
      ) h ON h.company_id = a.id
      WHERE a.is_excluded = FALSE
        AND fn.source != 'a16z_build'
        AND (fn.amount_usd IS NULL OR fn.amount_usd <= 100000000)
        AND NOT EXISTS (
          SELECT 1 FROM edgar_filings ef WHERE ef.accelerator_id = a.id
        )
      ORDER BY a.id, fn.published_at DESC
    ) accel_announced

  `);
  return rows;
}
