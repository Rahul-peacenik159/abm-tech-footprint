-- 00_schema.sql
-- Creates the shared ABM tables. Every repo in this project writes to the same
-- `accounts` and `signals` tables, so bundles can be combined later.
--
-- Replace YOUR_PROJECT with your Google Cloud project id, then run once:
--   bq query --use_legacy_sql=false < bigquery/00_schema.sql

CREATE SCHEMA IF NOT EXISTS `YOUR_PROJECT.abm`
OPTIONS (description = 'Open ABM bundles: accounts, signals, scores');

-- Your target accounts. Load from your CRM export or sample-data/*.csv:
--   bq load --source_format=CSV --skip_leading_rows=1 YOUR_PROJECT:abm.accounts sample-data/accounts-hospitality.csv domain:STRING,company:STRING,segment:STRING
CREATE TABLE IF NOT EXISTS `YOUR_PROJECT.abm.accounts` (
  domain   STRING NOT NULL OPTIONS (description = 'Registrable domain, lowercase, no www (example.com)'),
  company  STRING,
  segment  STRING OPTIONS (description = 'Your own segment / industry label'),
  tier     STRING OPTIONS (description = 'Optional existing tier, e.g. tier_1'),
  owner    STRING OPTIONS (description = 'Optional account owner')
);

-- One row per signal. Same columns the Python CLI writes to out/signals.jsonl:
--   bq load --source_format=NEWLINE_DELIMITED_JSON YOUR_PROJECT:abm.signals out/signals.jsonl
CREATE TABLE IF NOT EXISTS `YOUR_PROJECT.abm.signals` (
  account_domain STRING NOT NULL,
  signal_type    STRING NOT NULL OPTIONS (description = 'tech_detected | tech_added | tech_removed | gap | subdomain_new | pagespeed_mobile'),
  signal_value   STRING OPTIONS (description = 'Tool id, category, subdomain or score'),
  tool_name      STRING,
  category       STRING,
  role           STRING OPTIONS (description = 'competitor | complement | neutral | gap'),
  weight         INT64,
  play           STRING OPTIONS (description = 'Suggested play from the stack pack'),
  source         STRING OPTIONS (description = 'homepage | headers | dns_txt | spf | dns_mx | crtsh | pagespeed | httparchive | snapshot_diff'),
  evidence       STRING OPTIONS (description = 'The pattern or record that matched'),
  evidence_url   STRING,
  pack           STRING,
  observed_at    TIMESTAMP NOT NULL
)
PARTITION BY DATE(observed_at)
CLUSTER BY account_domain, signal_type;
