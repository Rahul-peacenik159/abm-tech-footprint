-- 30_account_scores.sql
-- One row per account: score, tier and the play to run this week.
-- Built from the last 30 days of signals, newest evidence first.
--
-- Save as a view so your CRM sync / dashboard always reads fresh scores:
--   CREATE OR REPLACE VIEW `YOUR_PROJECT.abm.tech_footprint_scores` AS <query below>

WITH recent AS (
  SELECT *
  FROM `YOUR_PROJECT.abm.signals`
  WHERE observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
),

-- keep one row per account + signal so repeated weekly scans do not double count
dedup AS (
  SELECT * EXCEPT (rn) FROM (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY account_domain, signal_type, signal_value ORDER BY observed_at DESC) AS rn
    FROM recent
  ) WHERE rn = 1
),

scored AS (
  SELECT
    account_domain,
    LEAST(100, SUM(weight)) AS footprint_score,
    ARRAY_AGG(IF(weight > 0, play, NULL) IGNORE NULLS ORDER BY weight DESC LIMIT 1)[SAFE_OFFSET(0)] AS top_play,
    STRING_AGG(DISTINCT IF(signal_type = 'tech_detected' AND role = 'competitor', tool_name, NULL), '; ') AS competitors,
    STRING_AGG(DISTINCT IF(signal_type = 'tech_detected' AND role = 'complement', tool_name, NULL), '; ') AS complements,
    STRING_AGG(DISTINCT IF(signal_type = 'gap', signal_value, NULL), '; ')                                AS gaps,
    STRING_AGG(DISTINCT IF(signal_type IN ('tech_added', 'tech_removed'),
                           CONCAT(IF(signal_type = 'tech_added', '+', '-'), tool_name), NULL), '; ')       AS changes,
    MAX(observed_at) AS last_signal_at
  FROM dedup
  GROUP BY account_domain
)

SELECT
  a.domain AS account_domain,
  a.company,
  a.segment,
  COALESCE(s.footprint_score, 0) AS footprint_score,
  CASE
    WHEN s.footprint_score >= 50 THEN 'tier_1'
    WHEN s.footprint_score >= 25 THEN 'tier_2'
    ELSE 'tier_3'
  END AS footprint_tier,      -- maps to HubSpot hs_ideal_customer_profile values
  s.top_play,
  s.competitors,
  s.complements,
  s.gaps,
  s.changes,
  s.last_signal_at
FROM `YOUR_PROJECT.abm.accounts` a
LEFT JOIN scored s ON s.account_domain = LOWER(a.domain)
ORDER BY footprint_score DESC;
