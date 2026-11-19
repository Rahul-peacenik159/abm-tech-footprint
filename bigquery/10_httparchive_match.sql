-- 10_httparchive_match.sql  (template)
--
-- Matches your accounts against HTTP Archive's monthly crawl of millions of
-- websites, which already runs Wappalyzer-style tech detection on every page.
-- The data is public; you only pay for the bytes your query scans.
--
-- Do not run this file directly. Generate a ready-to-run version for a pack:
--   python -m footprint httparchive-sql --pack hospitality \
--     --accounts-table YOUR_PROJECT.abm.accounts \
--     --signals-table  YOUR_PROJECT.abm.signals  --out hospitality_ha.sql
--
-- COST GUARDRAILS (read docs/bigquery-cost-guardrails.md):
--   1. Always dry-run first:  bq query --use_legacy_sql=false --dry_run < hospitality_ha.sql
--   2. Always cap spend:      bq query --use_legacy_sql=false --maximum_bytes_billed=200000000000 < hospitality_ha.sql
--   3. Never remove the date / client / is_root_page filters below. The table
--      is partitioned by date and clustered by client and is_root_page.

DECLARE crawl_date DATE DEFAULT DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH);
-- If last month's crawl is not published yet, set an older month, e.g.:
-- SET crawl_date = DATE '2026-09-01';

INSERT INTO `{{SIGNALS_TABLE}}`
  (account_domain, signal_type, signal_value, tool_name, category, role,
   weight, play, source, evidence, evidence_url, pack, observed_at)

WITH tool_map AS (
  SELECT * FROM UNNEST([
{{TOOL_MAP}}
  ])
),

targets AS (
  SELECT DISTINCT LOWER(domain) AS domain
  FROM `{{ACCOUNTS_TABLE}}`
),

crawl AS (
  SELECT
    NET.REG_DOMAIN(page) AS domain,
    page,
    t.technology
  FROM `httparchive.crawl.pages`, UNNEST(technologies) AS t
  WHERE date = crawl_date
    AND client = 'mobile'
    AND is_root_page
)

SELECT DISTINCT
  c.domain                         AS account_domain,
  'tech_detected'                  AS signal_type,
  m.tool_id                        AS signal_value,
  c.technology                     AS tool_name,
  m.category                       AS category,
  m.role                           AS role,
  CASE m.role WHEN 'competitor' THEN 30 WHEN 'complement' THEN 15 ELSE 0 END AS weight,
  CASE m.role WHEN 'competitor' THEN 'displacement_sequence'
              WHEN 'complement' THEN 'integration_pitch' ELSE '' END       AS play,
  'httparchive'                    AS source,
  CONCAT('HTTP Archive crawl ', CAST(crawl_date AS STRING)) AS evidence,
  c.page                           AS evidence_url,
  '{{PACK}}'                       AS pack,
  CURRENT_TIMESTAMP()              AS observed_at
FROM crawl c
JOIN targets  USING (domain)
JOIN tool_map m ON LOWER(m.technology) = LOWER(c.technology);
