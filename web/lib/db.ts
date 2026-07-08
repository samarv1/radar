import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// Deduplicates accelerator_companies by normalized website, aggregates all
// accelerators into an array, and surfaces the worst company_status.
const ACCEL_META_CTE = `
  accel_meta AS (
    SELECT
      regexp_replace(lower(website), '^https?://(www\\.)?|/+$', '', 'g') AS norm_site,
      array_agg(DISTINCT accelerator ORDER BY accelerator) AS accelerators,
      MAX(CASE WHEN company_status IS NOT NULL AND company_status != 'Active'
          THEN company_status END) AS worst_status
    FROM accelerator_companies
    WHERE website IS NOT NULL AND length(website) > 8
    GROUP BY 1
  )`;

// Job counts with all categories + timing columns (used in hiring feed).
const JOB_COUNTS_FULL = `
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
  FROM job_listings GROUP BY company_id`;

// Job counts for the four main role categories only (used in raised feed).
const JOB_COUNTS_BASIC = `
  SELECT company_id,
    SUM(CASE WHEN category = 'engineering' THEN 1 ELSE 0 END) AS eng,
    SUM(CASE WHEN category = 'product'     THEN 1 ELSE 0 END) AS product,
    SUM(CASE WHEN category = 'gtm'         THEN 1 ELSE 0 END) AS gtm,
    SUM(CASE WHEN category = 'other'       THEN 1 ELSE 0 END) AS other
  FROM job_listings GROUP BY company_id`;

export type Company = {
  id: number;
  name: string;
  website: string | null;
  accelerator: string;
  accelerators: string[];
  batch: string | null;
  careers_ats: string | null;
  careers_url: string | null;
  amount_raised: number | null;
  round_type: string | null;
  date_filed: string;
  date_source?: string;
  created_at: string;
  company_status: string | null;
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
    WITH ${ACCEL_META_CTE}
    SELECT * FROM (
      SELECT DISTINCT ON (COALESCE(am.norm_site, a.id::text))
        a.id, a.name, COALESCE(a.website, fn_site.website) AS website,
        a.accelerator,
        COALESCE(am.accelerators, ARRAY[a.accelerator]) AS accelerators,
        a.batch, a.careers_ats, a.careers_url, a.created_at::text,
        a.tags, a.company_status,
        COALESCE(ef_latest.amount_raised, fn_amt.amount_usd)::float AS amount_raised,
        a.round_type AS round_type,
        COALESCE(h.latest_posted_at::date::text, h.latest_first_seen_at::date::text, a.careers_scraped_at::date::text) AS date_filed,
        CASE
          WHEN h.latest_posted_at IS NOT NULL THEN 'posted'
          WHEN h.latest_first_seen_at IS NOT NULL THEN 'discovered'
          ELSE 'scraped'
        END AS date_source,
        FALSE AS has_edgar,
        COALESCE(h.eng, 0)::int      AS eng_count,
        COALESCE(h.product, 0)::int  AS product_count,
        COALESCE(h.gtm, 0)::int      AS gtm_count,
        COALESCE(h.other, 0)::int    AS other_count,
        COALESCE(h.intern, 0)::int   AS intern_count,
        COALESCE(h.new_grad, 0)::int AS new_grad_count,
        h.latest_posted_at, h.latest_first_seen_at, h.latest_scraped_at
      FROM accelerator_companies a
      LEFT JOIN accel_meta am
        ON regexp_replace(lower(a.website), '^https?://(www\\.)?|/+$', '', 'g') = am.norm_site
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
      JOIN (${JOB_COUNTS_FULL}) h ON h.company_id = a.id
      WHERE a.is_excluded = FALSE
        AND (
          -- Companies with confirmed open roles scraped in the last 90 days
          (COALESCE(h.eng, 0) + COALESCE(h.product, 0) + COALESCE(h.gtm, 0) + COALESCE(h.other, 0) + COALESCE(h.intern, 0) + COALESCE(h.new_grad, 0)) > 0
          AND COALESCE(h.latest_posted_at, h.latest_first_seen_at, h.latest_scraped_at) >= NOW() - INTERVAL '90 days'
          -- TODO: also surface yc_is_hiring=true companies once we track yc_is_hiring_since
          -- so we can apply a matching 90-day recency gate on the hiring signal itself.
          -- OR (a.yc_is_hiring = TRUE AND a.yc_is_hiring_since >= NOW() - INTERVAL '90 days')
        )
        AND (
          -- companies with a website group: exclude if any entry has a bad status
          (am.norm_site IS NOT NULL AND am.worst_status IS NULL)
          OR
          -- companies without a website (no group): check individual status
          (am.norm_site IS NULL AND (a.company_status IS NULL OR a.company_status = 'Active'))
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
      ORDER BY COALESCE(am.norm_site, a.id::text),
               COALESCE(h.latest_posted_at, h.latest_first_seen_at, h.latest_scraped_at) DESC NULLS LAST
    ) deduped
    ORDER BY COALESCE(latest_posted_at, latest_first_seen_at, latest_scraped_at) DESC NULLS LAST
  `);
  return rows;
}

export async function getFeed(): Promise<Company[]> {
  const { rows } = await pool.query<Company>(`
    WITH ${ACCEL_META_CTE}
    SELECT * FROM (
      -- Accelerator-backed companies with EDGAR filings (deduped by website)
      SELECT * FROM (
        SELECT DISTINCT ON (COALESCE(am.norm_site, a.id::text))
          a.id, a.name, COALESCE(a.website, fn_site.website) AS website,
          a.accelerator,
          COALESCE(am.accelerators, ARRAY[a.accelerator]) AS accelerators,
          a.batch, a.careers_ats, a.careers_url, a.created_at::text,
          a.company_status,
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
        LEFT JOIN accel_meta am
          ON regexp_replace(lower(a.website), '^https?://(www\\.)?|/+$', '', 'g') = am.norm_site
        LEFT JOIN (${JOB_COUNTS_BASIC}) h ON h.company_id = a.id
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
          AND e.date_filed >= (NOW() AT TIME ZONE 'UTC')::date - INTERVAL '90 days'
          AND (
            (am.norm_site IS NOT NULL AND am.worst_status IS NULL)
            OR (am.norm_site IS NULL AND (a.company_status IS NULL OR a.company_status = 'Active'))
          )
        ORDER BY COALESCE(am.norm_site, a.id::text), e.date_filed DESC
      ) accel_inner
    ) accel

    UNION ALL

    -- Non-accelerator EDGAR filings validated by TC/PH match or Other Technology industry group
    SELECT * FROM (
      SELECT DISTINCT ON (ef.company_name)
        -ef.id        AS id,
        ef.company_name AS name,
        COALESCE(fn.website, ph.website) AS website,
        ef.standalone_source AS accelerator,
        ARRAY[ef.standalone_source]::text[] AS accelerators,
        NULL::text    AS batch,
        cc.careers_ats AS careers_ats,
        cc.careers_url AS careers_url,
        ef.created_at::text,
        NULL::text    AS company_status,
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
        CASE ef.industry_group
          WHEN 'Other Technology'                    THEN ARRAY['saas', 'b2b']
          WHEN 'Computers'                           THEN ARRAY['saas', 'hardware']
          WHEN 'Business Services'                   THEN ARRAY['b2b', 'saas']
          WHEN 'Telecommunications'                  THEN ARRAY['saas', 'b2b']
          WHEN 'Biotechnology'                       THEN ARRAY['biotech', 'health']
          WHEN 'Other Health Care'                   THEN ARRAY['health']
          WHEN 'Hospitals and Physicians'            THEN ARRAY['health']
          WHEN 'Pharmaceuticals'                     THEN ARRAY['pharma', 'health']
          WHEN 'Insurance'                           THEN ARRAY['insurtech', 'fintech']
          WHEN 'Other Banking and Financial Services' THEN ARRAY['fintech']
          WHEN 'Manufacturing'                       THEN ARRAY['hardware']
          ELSE NULL::text[]
        END AS tags
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
      LEFT JOIN company_careers cc ON cc.website = COALESCE(fn.website, ph.website)
      WHERE ef.accelerator_id IS NULL
        AND ef.standalone_source IS NOT NULL
      ORDER BY ef.company_name, ef.date_filed DESC
    ) standalone

    UNION ALL

    -- funding_news-announced companies without a Form D filing yet (TechCrunch, Signalbase, etc.).
    -- Quality filters: real funding amount, short name (not a descriptor fragment),
    -- no comma/colon in name (descriptor prefix pattern), no VC fund keywords.
    -- Excludes companies already in the standalone EDGAR path to avoid duplicates.
    SELECT * FROM (
      SELECT DISTINCT ON (fn.company_name)
        fn.id + 1000000 AS id,
        fn.company_name AS name,
        fn.website      AS website,
        fn.source       AS accelerator,
        ARRAY[fn.source]::text[] AS accelerators,
        NULL::text      AS batch,
        cc.careers_ats  AS careers_ats,
        cc.careers_url  AS careers_url,
        fn.created_at::text,
        NULL::text      AS company_status,
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
        CASE
          WHEN fn.industry IN ('Financial Services', 'Payment Solutions')
            THEN ARRAY['fintech', 'payments']
          WHEN fn.industry = 'Insurance'
            THEN ARRAY['insurtech', 'fintech']
          WHEN fn.industry IN ('Healthcare', 'Hospitals and Health Care', 'Health and Wellness')
            THEN ARRAY['health']
          WHEN fn.industry = 'Biotechnology'
            THEN ARRAY['biotech', 'health']
          WHEN fn.industry = 'Education'
            THEN ARRAY['education', 'edtech']
          WHEN fn.industry IN ('Robotics', 'Engineering')
            THEN ARRAY['robotics', 'hardware']
          WHEN fn.industry ILIKE '%artificial intelligence%'
            THEN ARRAY['artificial intelligence', 'ai']
          WHEN fn.industry = 'E-commerce'
            THEN ARRAY['e-commerce', 'consumer']
          WHEN fn.industry IN ('CRM', 'Sales Platform', 'Job Search',
                               'Transportation, Logistics, Supply Chain and Storage')
            THEN ARRAY['saas', 'b2b']
          WHEN fn.industry ILIKE '%tech%' OR fn.industry ILIKE '%software%'
            THEN ARRAY['saas']
          ELSE NULL::text[]
        END AS tags
      FROM funding_news fn
      LEFT JOIN company_careers cc ON cc.website = fn.website
      WHERE fn.accelerator_id IS NULL
        AND fn.source != 'a16z_build'
        AND fn.published_at >= NOW() - INTERVAL '90 days'
        AND fn.amount_usd IS NOT NULL
        AND array_length(regexp_split_to_array(trim(fn.company_name), '\s+'), 1) <= 3
        AND fn.company_name NOT LIKE '%:%'
        AND fn.company_name NOT LIKE '%,%'
        AND fn.company_name !~* '\y(capital|fund|venture|ventures|partner|partners|vc)\y'
        AND fn.round_type IS NOT NULL
        AND fn.round_type NOT IN ('Series D', 'Series E')
        AND NOT (fn.round_type = 'Pre-Seed' AND fn.amount_usd IS NULL)
        AND (
          fn.source != 'signalbase'
          OR fn.industry IS NULL
          OR fn.industry ILIKE '%tech%'
          OR fn.industry ILIKE '%software%'
          OR fn.industry ILIKE '%artificial intelligence%'
          OR fn.industry ILIKE '%robotics%'
          OR fn.industry ILIKE '%digital%'
          OR fn.industry ILIKE '%platform%'
          OR fn.industry ILIKE '%data%'
          OR fn.industry IN (
            'CRM', 'E-commerce', 'Job Search', 'Payment Solutions', 'Engineering',
            'Financial Services', 'Healthcare', 'Biotechnology', 'Health and Wellness',
            'Scientific Services', 'Education', 'Insurance',
            'Transportation, Logistics, Supply Chain and Storage'
          )
        )
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
        a.id, a.name, COALESCE(a.website, fn.website) AS website, a.accelerator,
        ARRAY[a.accelerator]::text[] AS accelerators,
        a.batch, a.careers_ats, a.careers_url, a.created_at::text,
        a.company_status,
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
      LEFT JOIN (${JOB_COUNTS_BASIC}) h ON h.company_id = a.id
      WHERE a.is_excluded = FALSE
        AND fn.source != 'a16z_build'
        AND fn.published_at >= NOW() - INTERVAL '90 days'
        AND NOT EXISTS (
          SELECT 1 FROM edgar_filings ef WHERE ef.accelerator_id = a.id
        )
      ORDER BY a.id, fn.published_at DESC
    ) accel_announced

  `);
  return rows;
}
