-- 20_tech_changes.sql
-- Tools added or removed per account between the two most recent scans.
-- Works on any mix of sources (homepage scans, DNS, HTTP Archive).
-- Changes are usually the strongest ABM timing trigger.
--
-- Cheap: reads only your own `signals` table.

WITH detected AS (
  SELECT account_domain, signal_value AS tool_id, ANY_VALUE(tool_name) AS tool_name,
         ANY_VALUE(role) AS role, DATE(observed_at) AS scan_date
  FROM `YOUR_PROJECT.abm.signals`
  WHERE signal_type = 'tech_detected'
    AND observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 120 DAY)
  GROUP BY account_domain, tool_id, scan_date
),

scans AS (
  SELECT account_domain, scan_date,
         DENSE_RANK() OVER (PARTITION BY account_domain ORDER BY scan_date DESC) AS rnk
  FROM (SELECT DISTINCT account_domain, scan_date FROM detected)
),

latest   AS (SELECT d.* FROM detected d JOIN scans s USING (account_domain, scan_date) WHERE s.rnk = 1),
previous AS (SELECT d.* FROM detected d JOIN scans s USING (account_domain, scan_date) WHERE s.rnk = 2)

SELECT
  COALESCE(l.account_domain, p.account_domain) AS account_domain,
  COALESCE(l.tool_id, p.tool_id)               AS tool_id,
  COALESCE(l.tool_name, p.tool_name)           AS tool_name,
  COALESCE(l.role, p.role)                     AS role,
  IF(p.tool_id IS NULL, 'added', 'removed')    AS change,
  CASE
    WHEN p.tool_id IS NOT NULL AND p.role = 'competitor' THEN 'switch_window_outreach'
    ELSE 'timing_trigger'
  END                                          AS play,
  l.scan_date                                  AS latest_scan,
  p.scan_date                                  AS previous_scan
FROM latest l
FULL OUTER JOIN previous p
  ON l.account_domain = p.account_domain AND l.tool_id = p.tool_id
WHERE (l.tool_id IS NULL OR p.tool_id IS NULL)
  -- only accounts that have two scans to compare
  AND COALESCE(l.account_domain, p.account_domain) IN (SELECT account_domain FROM scans WHERE rnk = 2)
ORDER BY account_domain, change;
