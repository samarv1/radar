import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export type Company = {
  id: number;
  name: string;
  website: string | null;
  accelerator: string;
  batch: string | null;
  careers_ats: string | null;
  amount_raised: number | null;
  date_filed: string;
  eng_count: number;
  product_count: number;
  gtm_count: number;
  other_count: number;
};

export async function getFeed(): Promise<Company[]> {
  const { rows } = await pool.query<Company>(`
    SELECT DISTINCT ON (a.id)
      a.id, a.name, a.website, a.accelerator, a.batch,
      a.careers_ats,
      e.amount_raised, e.date_filed::text,
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
  `);
  return rows;
}
