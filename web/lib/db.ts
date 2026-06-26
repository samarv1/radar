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
  round_type: string | null;
  date_filed: string;
  date_source?: string;
  created_at: string;
  has_edgar: boolean;
  eng_count: number;
  product_count: number;
  gtm_count: number;
  other_count: number;
  intern_count: number;
  new_grad_count: number;
  tags: string[] | null;
};


export async function getHiringFeed(): Promise<Company[]> {
  const { rows } = await pool.query<Company>(`
    SELECT
      a.id, a.name, COALESCE(a.website, fn_site.website) AS website, a.accelerator, a.batch,
      a.careers_ats, a.careers_url, a.created_at::text,
      a.tags,
      COALESCE(ef_latest.amount_raised, fn_amt.amount_usd)::float AS amount_raised,
      a.round_type AS round_type,
      COALESCE(h.latest_posted_at::date::text, h.latest_first_seen_at::date::text, a.careers_scraped_at::date::text) AS date_filed,
      CASE WHEN h.latest_posted_at IS NOT NULL OR h.latest_first_seen_at IS NOT NULL THEN 'posted' ELSE 'scraped' END AS date_source,
      FALSE AS has_edgar,
      COALESCE(h.eng, 0)::int      AS eng_count,
      COALESCE(h.product, 0)::int  AS product_count,
      COALESCE(h.gtm, 0)::int      AS gtm_count,
      COALESCE(h.other, 0)::int    AS other_count,
      COALESCE(h.intern, 0)::int   AS intern_count,
      COALESCE(h.new_grad, 0)::int AS new_grad_count
    FROM accelerator_companies a
    LEFT JOIN LATERAL (
      SELECT website FROM funding_news
      WHERE accelerator_id = a.id AND website IS NOT NULL
      ORDER BY published_at DESC LIMIT 1
    ) fn_site ON TRUE
    LEFT JOIN LATERAL (
      SELECT amount_raised FROM edgar_filings
      WHERE accelerator_id = a.id
      ORDER BY date_filed DESC LIMIT 1
    ) ef_latest ON TRUE
    LEFT JOIN LATERAL (
      SELECT amount_usd FROM funding_news
      WHERE accelerator_id = a.id AND amount_usd IS NOT NULL
      ORDER BY published_at DESC LIMIT 1
    ) fn_amt ON TRUE
    JOIN (
      SELECT company_id,
        SUM(CASE WHEN category = 'engineering' THEN 1 ELSE 0 END) AS eng,
        SUM(CASE WHEN category = 'product'     THEN 1 ELSE 0 END) AS product,
        SUM(CASE WHEN category = 'gtm'         THEN 1 ELSE 0 END) AS gtm,
        SUM(CASE WHEN category = 'other'       THEN 1 ELSE 0 END) AS other,
        SUM(CASE WHEN category = 'intern'      THEN 1 ELSE 0 END) AS intern,
        SUM(CASE WHEN category = 'new_grad'    THEN 1 ELSE 0 END) AS new_grad,
        MAX(posted_at)      AS latest_posted_at,
        MAX(first_seen_at)  AS latest_first_seen_at,
        MAX(scraped_at)     AS latest_scraped_at
      FROM job_listings GROUP BY company_id
    ) h ON h.company_id = a.id
    WHERE a.is_excluded = FALSE
      AND (h.eng + h.product + h.gtm + h.other + h.intern + h.new_grad) > 0
      AND COALESCE(h.latest_posted_at, h.latest_first_seen_at, h.latest_scraped_at) >= NOW() - INTERVAL '90 days'
      -- Not already in the Raised feed (no EDGAR filing in last 90 days)
      AND NOT EXISTS (
        SELECT 1 FROM edgar_filings ef
        WHERE ef.accelerator_id = a.id
          AND ef.date_filed >= NOW() - INTERVAL '90 days'
      )
      -- Exclude known large raises
      AND NOT EXISTS (
        SELECT 1 FROM edgar_filings ef
        WHERE ef.accelerator_id = a.id
          AND ef.amount_raised > 100000000
      )
      AND (
        a.accelerator IN ('yc', 'techstars')
        OR (a.accelerator = 'a16z'
            AND (a.stage IS NULL
                 OR (a.stage NOT ILIKE '%growth%' AND a.stage NOT ILIKE '%exit%')))
        OR (a.accelerator = 'sequoia'
            AND (a.stage IS NULL OR a.stage IN ('Pre-Seed/Seed', 'Early')))
        OR a.accelerator IN ('pear', 'lightspeed')
      )
    ORDER BY h.latest_posted_at DESC NULLS LAST, h.latest_first_seen_at DESC NULLS LAST, h.latest_scraped_at DESC
  `);
  return rows;
}

export async function getFeed(): Promise<Company[]> {
  const { rows } = await pool.query<Company>(`
    SELECT * FROM (
      -- Accelerator-backed companies with EDGAR filings
      SELECT DISTINCT ON (a.id)
        a.id, a.name, COALESCE(a.website, fn_site.website) AS website, a.accelerator, a.batch,
        a.careers_ats, a.careers_url, a.created_at::text,
        COALESCE(e.amount_raised, fn_round.amount_usd)::float AS amount_raised,
        COALESCE(fn_round.round_type, a.round_type) AS round_type,
        e.date_filed::text,
        'raised'::text AS date_source,
        TRUE AS has_edgar,
        COALESCE(h.eng, 0)::int     AS eng_count,
        COALESCE(h.product, 0)::int AS product_count,
        COALESCE(h.gtm, 0)::int     AS gtm_count,
        COALESCE(h.other, 0)::int   AS other_count,
        0::int AS intern_count,
        0::int AS new_grad_count,
        a.tags
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
      LEFT JOIN LATERAL (
        SELECT round_type, amount_usd FROM funding_news
        WHERE accelerator_id = a.id AND round_type IS NOT NULL
        ORDER BY published_at DESC LIMIT 1
      ) fn_round ON TRUE
      LEFT JOIN LATERAL (
        SELECT website FROM funding_news
        WHERE accelerator_id = a.id AND website IS NOT NULL
        ORDER BY published_at DESC LIMIT 1
      ) fn_site ON TRUE
      WHERE a.is_excluded = FALSE
        AND (e.amount_raised IS NULL OR e.amount_raised <= 100000000)
        AND e.date_filed >= NOW() - INTERVAL '180 days'
      ORDER BY a.id, e.date_filed DESC
    ) accel

    UNION ALL

    -- Non-accelerator EDGAR filings validated by TC/PH match or Other Technology industry group
    SELECT * FROM (
      SELECT DISTINCT ON (ef.company_name)
        -ef.id        AS id,
        ef.company_name AS name,
        COALESCE(fn.website, ph.website) AS website,
        ef.standalone_source AS accelerator,
        NULL::text    AS batch,
        NULL::text    AS careers_ats,
        NULL::text    AS careers_url,
        ef.created_at::text,
        ef.amount_raised::float AS amount_raised,
        fn.round_type AS round_type,
        ef.date_filed::text,
        'raised'::text AS date_source,
        TRUE AS has_edgar,
        0::int AS eng_count,
        0::int AS product_count,
        0::int AS gtm_count,
        0::int AS other_count,
        0::int AS intern_count,
        0::int AS new_grad_count,
        NULL::text[] AS tags
      FROM edgar_filings ef
      LEFT JOIN LATERAL (
        SELECT website, round_type FROM funding_news
        WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(ef.company_name))
        ORDER BY created_at DESC LIMIT 1
      ) fn ON TRUE
      LEFT JOIN LATERAL (
        SELECT website FROM ph_launches
        WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(ef.company_name))
        ORDER BY created_at DESC LIMIT 1
      ) ph ON TRUE
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
        fn.website      AS website,
        'techcrunch'::text AS accelerator,
        NULL::text      AS batch,
        NULL::text      AS careers_ats,
        NULL::text      AS careers_url,
        fn.created_at::text,
        fn.amount_usd::float AS amount_raised,
        fn.round_type   AS round_type,
        fn.published_at::date::text AS date_filed,
        'announced'::text AS date_source,
        FALSE AS has_edgar,
        0::int AS eng_count,
        0::int AS product_count,
        0::int AS gtm_count,
        0::int AS other_count,
        0::int AS intern_count,
        0::int AS new_grad_count,
        NULL::text[] AS tags
      FROM funding_news fn
      WHERE fn.accelerator_id IS NULL
        AND fn.amount_usd IS NOT NULL
        AND fn.amount_usd <= 100000000
        AND array_length(regexp_split_to_array(trim(fn.company_name), '\s+'), 1) <= 3
        AND fn.company_name NOT LIKE '%:%'
        AND fn.company_name NOT LIKE '%,%'
        AND fn.company_name !~* '\y(capital|fund|venture|ventures|partner|partners|vc)\y'
        AND fn.round_type IS NOT NULL
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
        a.id, a.name, COALESCE(a.website, fn.website) AS website, a.accelerator, a.batch,
        a.careers_ats, a.careers_url, a.created_at::text,
        fn.amount_usd::float AS amount_raised,
        fn.round_type   AS round_type,
        fn.published_at::date::text AS date_filed,
        'announced'::text AS date_source,
        FALSE AS has_edgar,
        COALESCE(h.eng, 0)::int     AS eng_count,
        COALESCE(h.product, 0)::int AS product_count,
        COALESCE(h.gtm, 0)::int     AS gtm_count,
        COALESCE(h.other, 0)::int   AS other_count,
        0::int AS intern_count,
        0::int AS new_grad_count,
        a.tags
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
        AND fn.published_at >= NOW() - INTERVAL '180 days'
        AND NOT EXISTS (
          SELECT 1 FROM edgar_filings ef WHERE ef.accelerator_id = a.id
        )
      ORDER BY a.id, fn.published_at DESC
    ) accel_announced

  `);
  return rows;
}
