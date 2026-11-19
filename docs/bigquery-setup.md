# BigQuery setup and cost guardrails

BigQuery is optional. The CLI works on its own with CSV output. Use BigQuery when you want history across weeks, very large account lists, the HTTP Archive match, or a view your CRM / dashboard reads from.

## 1. One-time setup

1. Create (or pick) a Google Cloud project. The [BigQuery sandbox](https://cloud.google.com/bigquery/docs/sandbox) works without a credit card for small volumes.
2. Install the Google Cloud CLI and run `gcloud auth login` and `gcloud config set project YOUR_PROJECT`.
3. Replace `YOUR_PROJECT` in the files under `bigquery/` (or use `sed -i '' 's/YOUR_PROJECT/my-project/g' bigquery/*.sql` on macOS).
4. Create the tables:

```bash
bq query --use_legacy_sql=false < bigquery/00_schema.sql
```

## 2. Load data

```bash
bq load --source_format=CSV --skip_leading_rows=1 \
  YOUR_PROJECT:abm.accounts sample-data/accounts-hospitality.csv \
  domain:STRING,company:STRING,segment:STRING

python -m footprint scan --pack hospitality --accounts sample-data/accounts-hospitality.csv
bq load --source_format=NEWLINE_DELIMITED_JSON YOUR_PROJECT:abm.signals out/signals.jsonl
```

## 3. Cost guardrails (read before touching HTTP Archive)

Your own `accounts` and `signals` tables are tiny; queries on them cost nothing meaningful. **HTTP Archive is different:** its tables hold years of crawls of millions of pages, and an unfiltered query can scan many terabytes. People have run up four- and five-figure bills by accident.

Always:

1. **Dry run first.** `bq query --use_legacy_sql=false --dry_run < file.sql` prints the bytes it would scan, for free.
2. **Cap the bytes.** `--maximum_bytes_billed=200000000000` (200 GB) makes BigQuery refuse anything bigger instead of charging you. In the console: More > Query settings > Advanced > Maximum bytes billed.
3. **Keep the filters.** `httparchive.crawl.pages` is partitioned by `date` and clustered by `client` and `is_root_page`. The generated query filters on all three and selects only `page` and `technologies`. Don't add `SELECT *`, `lighthouse`, `payload` or `custom_metrics`.
4. **Explore with samples.** Add `TABLESAMPLE SYSTEM (0.1 PERCENT)` when browsing technology names.
5. **Set a budget alert** on the Google Cloud project (Billing > Budgets & alerts).

BigQuery on-demand pricing includes a free tier (currently the first 1 TiB scanned per month). Check current pricing for your region before running large jobs.

## 4. HTTP Archive match

```bash
python -m footprint httparchive-sql --pack hospitality \
  --accounts-table YOUR_PROJECT.abm.accounts \
  --signals-table  YOUR_PROJECT.abm.signals --out ha.sql

bq query --use_legacy_sql=false --dry_run < ha.sql
bq query --use_legacy_sql=false --maximum_bytes_billed=200000000000 < ha.sql
```

Only tools with an `httparchive:` name in the pack are matched. If the latest month isn't published yet, the query finds nothing: edit `SET crawl_date = DATE 'YYYY-MM-01'` to an earlier month.

## 5. Changes and scores

```bash
bq query --use_legacy_sql=false < bigquery/20_tech_changes.sql
bq query --use_legacy_sql=false < bigquery/30_account_scores.sql
```

Save `30_account_scores.sql` as a view (`CREATE OR REPLACE VIEW YOUR_PROJECT.abm.tech_footprint_scores AS ...`) and point your CRM sync, Looker Studio dashboard or reverse-ETL at it. `footprint_tier` uses `tier_1` / `tier_2` / `tier_3`, the same values as HubSpot's `hs_ideal_customer_profile` property.
