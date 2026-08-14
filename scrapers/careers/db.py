"""
DB access for the careers pipeline: which companies/websites need scraping,
and persisting scrape results (job listings + careers_ats/url status).
"""

from scrapers.careers.ats_fetchers import REAL_ATS
from scrapers.careers.categorize import categorize

_KNOWN_ATS_LIST = "','".join(REAL_ATS)
VALID_ACCELERATORS = frozenset({"yc", "a16z", "sequoia", "lightspeed", "pear", "techstars"})


def get_pending_companies(
    conn,
    refresh_after_days: int | None = 3,
    rediscover_after_days: int | None = 21,
    hiring_sweep: bool = False,
    accelerator: str | None = None,
) -> list[dict]:
    # Three-tier staleness: known ATS refreshes cheaply and often; not_found staggers long;
    # NULL is always picked up (discovered once on first encounter).
    staleness_parts = ["a.careers_scraped_at IS NULL"]
    if refresh_after_days is not None:
        staleness_parts.append(
            f"(a.careers_ats IN ('{_KNOWN_ATS_LIST}') "
            f"AND a.careers_scraped_at < NOW() - INTERVAL '{refresh_after_days} days')"
        )
    if rediscover_after_days is not None:
        staleness_parts.append(
            f"(a.careers_ats = 'not_found' "
            f"AND a.careers_scraped_at < NOW() - INTERVAL '{rediscover_after_days} days')"
        )
    staleness = "AND (" + " OR ".join(staleness_parts) + ")"

    if accelerator and accelerator not in VALID_ACCELERATORS:
        raise ValueError(f"Unknown accelerator: {accelerator!r}. Valid: {sorted(VALID_ACCELERATORS)}")
    accel_filter = f"AND a.accelerator = '{accelerator}'" if accelerator else ""

    if hiring_sweep:
        # Sweep accelerator companies regardless of EDGAR status.
        # Exclude companies with known large raises (>$100M EDGAR filing).
        # Per-accelerator strategy:
        #   YC/Techstars  — all (no batch filter; $100M check handles large exits)
        #   a16z          — exclude stage containing 'Growth' or 'EXIT'
        #   Sequoia       — only Pre-Seed/Seed or Early stage
        #   Pear/Lightspeed — include all
        sql = f"""
            SELECT DISTINCT a.id, a.name, a.website, a.careers_ats, a.careers_url
            FROM accelerator_companies a
            WHERE a.is_excluded = FALSE
              {staleness}
              {accel_filter}
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
            ORDER BY a.id
        """
    else:
        # Cover all accelerator companies that could appear in the raised feed:
        # those with any EDGAR filing ≤ $100M OR recent funding news (last 180 days).
        # This replaces the old JOIN on edgar_filings so accelerator-announced
        # companies (no Form D yet) are also scraped.
        sql = f"""
            SELECT DISTINCT a.id, a.name, a.website, a.careers_ats, a.careers_url
            FROM accelerator_companies a
            WHERE a.is_excluded = FALSE
              {staleness}
              {accel_filter}
              AND (
                EXISTS (
                    SELECT 1 FROM edgar_filings e
                    WHERE e.accelerator_id = a.id
                      AND (e.amount_raised IS NULL OR e.amount_raised <= 100000000)
                )
                OR EXISTS (
                    SELECT 1 FROM funding_news fn
                    WHERE fn.accelerator_id = a.id
                      AND fn.published_at >= NOW() - INTERVAL '180 days'
                )
              )
            ORDER BY a.id
        """
    with conn.cursor() as cur:
        cur.execute(sql)
        return [
            {"id": r[0], "name": r[1], "website": r[2], "careers_ats": r[3], "careers_url": r[4]}
            for r in cur.fetchall()
        ]


def clear_jobs(conn, company_id: int):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM job_listings WHERE company_id = %s", (company_id,))


def sync_jobs(conn, company_id: int, ats: str, jobs: list[dict]):
    """Diff-based upsert: insert new jobs (preserving first_seen_at), delete removed ones."""
    fresh_ids = {j["job_id"] for j in jobs}

    with conn.cursor() as cur:
        cur.execute(
            "SELECT job_id FROM job_listings WHERE company_id = %s AND ats = %s",
            (company_id, ats),
        )
        existing_ids = {row[0] for row in cur.fetchall()}

        removed = existing_ids - fresh_ids
        if removed:
            cur.execute(
                "DELETE FROM job_listings WHERE company_id = %s AND ats = %s AND job_id = ANY(%s)",
                (company_id, ats, list(removed)),
            )

        # Insert new jobs (first_seen_at = NOW() marks when we first noticed them)
        new_jobs = [j for j in jobs if j["job_id"] not in existing_ids]
        if new_jobs:
            insert_sql = """
                INSERT INTO job_listings
                    (company_id, ats, job_id, title, department, location, category,
                     job_url, posted_at, first_seen_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (company_id, ats, job_id) DO NOTHING
            """
            for j in new_jobs:
                cat = categorize(j["title"])
                cur.execute(insert_sql, (
                    company_id, ats, j["job_id"], j["title"],
                    j["department"], j["location"], cat, j["job_url"],
                    j.get("posted_at"),
                ))

        if fresh_ids:
            cur.execute(
                "UPDATE job_listings SET scraped_at = NOW() WHERE company_id = %s AND ats = %s",
                (company_id, ats),
            )


def update_careers_status(conn, company_id: int, ats: str, url: str | None):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE accelerator_companies
            SET careers_ats = %s, careers_url = %s, careers_scraped_at = NOW()
            WHERE id = %s
        """, (ats, url, company_id))


def get_pending_standalone_websites(
    conn,
    rediscover_after_days: int | None = 21,
) -> list[dict]:
    """Return TC/standalone company websites that need careers scraping.

    Covers the two non-accelerator branches of the raised feed:
      - TC-only announced (funding_news with no accelerator_id)
      - Standalone EDGAR companies validated by TC/PH (edgar_filings.standalone_source IS NOT NULL)
    Results are stored in company_careers keyed by website.
    """
    staleness_parts = ["cc.website IS NULL"]
    if rediscover_after_days is not None:
        staleness_parts.append(
            f"cc.careers_scraped_at < NOW() - INTERVAL '{rediscover_after_days} days'"
        )
    staleness = " OR ".join(staleness_parts)

    sql = f"""
        WITH combined AS (
            -- TC/Signalbase-only announced companies (mirrors dashboard tc_only filters)
            SELECT fn.website, fn.company_name AS name
            FROM funding_news fn
            WHERE fn.accelerator_id IS NULL
              AND fn.source != 'a16z_build'
              AND fn.website IS NOT NULL
              AND fn.amount_usd IS NOT NULL
              AND fn.round_type IS NOT NULL
              AND fn.round_type NOT IN ('Series D', 'Series E')
              AND array_length(regexp_split_to_array(trim(fn.company_name), E'\\s+'), 1) <= 3
              AND fn.company_name NOT LIKE '%:%'
              AND fn.company_name NOT LIKE '%,%'
              AND fn.company_name !~* '\\y(capital|fund|venture|ventures|partner|partners|vc)\\y'
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

            UNION

            -- Standalone EDGAR companies (website from funding_news or PH match)
            SELECT COALESCE(fn2.website, ph.website), ef.company_name
            FROM edgar_filings ef
            LEFT JOIN LATERAL (
                SELECT website FROM funding_news
                WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(ef.company_name))
                ORDER BY created_at DESC LIMIT 1
            ) fn2 ON TRUE
            LEFT JOIN LATERAL (
                SELECT website FROM ph_launches
                WHERE LOWER(TRIM(product_name)) = LOWER(TRIM(ef.company_name))
                ORDER BY created_at DESC LIMIT 1
            ) ph ON TRUE
            WHERE ef.accelerator_id IS NULL
              AND ef.standalone_source IS NOT NULL
              AND COALESCE(fn2.website, ph.website) IS NOT NULL
        )
        SELECT DISTINCT ON (c.website)
          c.website, c.name, cc.careers_ats, cc.careers_url
        FROM combined c
        LEFT JOIN company_careers cc ON cc.website = c.website
        WHERE ({staleness})
        ORDER BY c.website
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return [
            {"website": r[0], "name": r[1], "careers_ats": r[2], "careers_url": r[3]}
            for r in cur.fetchall()
        ]


def update_standalone_careers(conn, website: str, ats: str | None, url: str | None):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO company_careers (website, careers_ats, careers_url, careers_scraped_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (website) DO UPDATE SET
                careers_ats = EXCLUDED.careers_ats,
                careers_url = EXCLUDED.careers_url,
                careers_scraped_at = NOW()
        """, (website, ats, url))
