# abm-tech-footprint

**See what your target accounts run, what they just added or dropped, and what they're missing, using only free, public data. Then turn it into ABM plays.**

Built for marketers and GTM engineers doing account-based marketing. No paid data subscription needed: the bundle reads what every company already exposes publicly (website scripts, DNS records, certificate logs, page speed, and the HTTP Archive crawl in BigQuery).

```
your account list ──► scan (website, DNS, cert logs, speed) ──► signals ──► score + play per account
                         + HTTP Archive in BigQuery (monthly)               (CSV, BigQuery, CRM)
```

> Part of an open set of ABM bundles. Every bundle writes to the same `accounts` and `signals` tables, so they stack. See [Roadmap](#roadmap).

---

## What you get

| Piece | What it does |
|---|---|
| `footprint/` | Python CLI: scans accounts, detects tools, scores, writes CSV + JSONL |
| `stack-packs/` | YAML "industry packs": fingerprints, your competitors/complements, gap rules, plays. 7 industries plus security-compliance and email-deliverability, and a template for any other |
| `bigquery/` | Shared schema, HTTP Archive match (generated per pack), tool-change diff, account scores view |
| `n8n/` | Importable weekly workflow (website + DNS checks, writes to BigQuery) |
| `collectors/` | Browser and DNS collectors for sites or networks that block the scanner |
| `docs/` | How it works, who it helps, how to build a pack for any industry, security and email checks, BigQuery cost guardrails |

## Quickstart (10 minutes, no keys needed)

```bash
git clone https://github.com/Rahul-peacenik159/abm-tech-footprint.git
cd abm-tech-footprint
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# see the industry packs
python -m footprint packs

# scan the sample hotel list with the hospitality pack
python -m footprint scan --pack hospitality --accounts sample-data/accounts-hospitality.csv
```

Open `out/accounts_summary.csv` in Google Sheets or Excel. One row per account, sorted by score:

| account_domain | score | top_play | competitors | complements | gaps | changes | all_tools |
|---|---|---|---|---|---|---|---|
| example-hotel.com | 45 | displacement_sequence | Asksuite | SynXis Booking Engine | | | Google Tag Manager; Meta Pixel; SynXis...; Asksuite; WordPress |
| other-hotel.com | 20 | revenue_leak_audit | | | chat | | Google Analytics; Cloudbeds |

**Your own accounts:** export a CSV with a `domain` column from your CRM and pass it with `--accounts`.
**Your own product:** edit the `seller:` block at the top of the pack (competitors, complements, must-have categories). That's what turns raw tech data into plays.
**Weekly changes:** run the same command again next week. The second run adds `tech_added` / `tech_removed` signals, usually the best timing trigger.

Useful flags:

```bash
--crtsh          # also check certificate logs for new subdomains (book., events., apply.)
--pagespeed      # also get mobile speed score (set PAGESPEED_API_KEY in .env for higher quota)
--domains a.com b.com   # scan domains without a CSV
--limit 20       # try a few first
--render         # open pages in headless Chromium to catch tools loaded by tag managers
                 #   (pip install -r requirements-render.txt && python -m playwright install chromium)
--from-raw raw.json --dns-raw dns.json   # use data collected in your browser (collectors/), no network needed
```

## Run it on GitHub instead (no installs)

The repo includes a **scan** workflow that runs on GitHub's servers: **Actions** tab > **scan** > **Run workflow**, pick a pack and an account list (or type domains), and the results table appears on the run's Summary page with CSVs to download. Steps, private-list advice and weekly scheduling: [docs/run-on-github.md](docs/run-on-github.md).

## How it works

Five free sources, each catching a different layer. Details in [docs/how-it-works.md](docs/how-it-works.md).

| Source | How | What it reveals | Cost |
|---|---|---|---|
| **Live website check** | Fetches the homepage (plus optional pages) and matches scripts, links and headers against pack fingerprints | Chat, booking, forms, video, analytics, pixels, CMS, ecommerce apps, CDN | Free |
| **DNS records** | TXT, SPF and MX lookups | Email provider (Google vs Microsoft), sending tools, SaaS sign-ups via verification tokens (Atlassian, DocuSign, Zoom, Slack...) | Free |
| **Certificate logs (crt.sh)** | Every SSL certificate is public, so new subdomains show up | Launches and new tools: `book.`, `events.`, `apply.`, `app.` | Free |
| **PageSpeed Insights** | Google runs Lighthouse on the homepage | Slow mobile sites, a strong "you're losing conversions" angle | Free (API key optional) |
| **HTTP Archive (BigQuery)** | Monthly crawl of millions of sites with tech detection already run | Same as the website check, at scale, without hitting any site yourself | Data is free, you pay BigQuery scan cost (1 TB/month free tier) |

**What free data cannot see:** back-office systems (CRM, ERP, PMS, payroll) that never touch the website. For those, use job postings (the `abm-hiring-signals` bundle) or a paid source as an optional add-on.

## Who this helps

The rule: **free tech data works when the product you sell, the competitor you replace, or the tools you plug into show up on the prospect's website, DNS or subdomains.**

| Seller | What they see on prospect sites | Play |
|---|---|---|
| Hospitality tech | Booking engine, chat/messaging, reviews, RFP tools | Replace a competitor widget; pitch hotels with no direct booking or chat |
| Ecommerce apps | Shopify/Magento, Klaviyo, Yotpo, Klarna, Recharge | Integration pitch; displacement |
| Martech / adtech | GA4, Segment, Optimizely, ad pixels | Maturity tiering; displacement |
| Chat, forms, scheduling | Intercom, Drift, Calendly, Chili Piper | Displacement; "no chat on pricing page" gap |
| Video platforms | Wistia, Vidyard, Vimeo, YouTube embeds | Upgrade or replace the player |
| Web agencies / CMS | Old WordPress, slow PageSpeed, no tag manager | Site audit outreach |
| Restaurant tech | Toast, ChowNow, OpenTable, `order.` subdomains | Commission-saving switch |
| Auto dealer tech | Dealer.com / DealerOn sites, chat, trade-in | Platform swap, add-ons |
| Practice tech (dental, clinics) | Online booking, intake, reviews | "No online booking" gap |
| Higher ed tech | Slate portals, chatbots, virtual tours | Enrollment-season timing |
| Security / compliance | CDN headers, consent tools | Compliance gap, renewal timing |
| Email / deliverability | MX + SPF records | Platform-fit lists, audits |

Full analysis, including who it won't help: [docs/who-benefits.md](docs/who-benefits.md).

## The four plays

| Signal | Meaning | Default play |
|---|---|---|
| **Competitor found** | They run a tool you replace | `displacement_sequence` |
| **Complement found** | They run a tool you integrate with | `integration_pitch` |
| **Gap** | A category you expect is missing entirely | `<industry>_audit` ("you're leaving money on the table") |
| **Change** | Tool added or removed since last scan (competitor removed = switch window) | `timing_trigger` / `switch_window_outreach` |

Plays are just labels you choose in the pack. Map them to your sequences, ad audiences or 1:1 pages.

## Industry packs

| Pack | For | Example seller in the pack |
|---|---|---|
| `hospitality` | Hotels, resorts, management companies | AI guest messaging / revenue capture |
| `ecommerce` | DTC brands, online retailers | Reviews / UGC app |
| `b2b-saas` | B2B software companies | Visitor identification |
| `restaurants` | Restaurant groups | Commission-free ordering |
| `auto-dealers` | Dealerships, dealer groups | Dealer chat / lead response |
| `healthcare-practices` | Dental, clinics, PT groups | Online patient scheduling |
| `higher-ed` | Universities, online programs | Admissions chatbot |
| `security-compliance` | Companies selling to enterprises (security posture, CDN/WAF, trust center, consent) | Compliance automation / trust center |
| `email-deliverability` | Any company that sends email (provider, gateways, senders, DMARC/SPF/MTA-STS/BIMI) | DMARC / email authentication platform |

The last two also run **posture checks**: website security headers and `security.txt`, and SPF/DMARC/MTA-STS/BIMI policy. See [docs/security-and-email-checks.md](docs/security-and-email-checks.md).

**Any other industry:** copy `stack-packs/_template.yaml`, then use `discover` to learn fingerprints from companies you know:

```bash
python -m footprint discover somecustomer.com --pack b2b-saas
```

It lists every third-party host the site loads and which tools the pack already recognises. Hosts that repeat across a tool's customers are its fingerprint. Guide: [docs/stack-packs.md](docs/stack-packs.md). Prompt to draft a whole pack with an AI assistant: [docs/build-a-pack-with-ai.md](docs/build-a-pack-with-ai.md).

## BigQuery (optional, for scale and history)

```bash
# 1. create tables (edit YOUR_PROJECT first)
bq query --use_legacy_sql=false < bigquery/00_schema.sql

# 2. load accounts and the CLI's signals
bq load --source_format=CSV --skip_leading_rows=1 YOUR_PROJECT:abm.accounts sample-data/accounts-hospitality.csv domain:STRING,company:STRING,segment:STRING
bq load --source_format=NEWLINE_DELIMITED_JSON YOUR_PROJECT:abm.signals out/signals.jsonl

# 3. add HTTP Archive matches for a pack (dry run first, always cap bytes)
python -m footprint httparchive-sql --pack hospitality --accounts-table YOUR_PROJECT.abm.accounts --signals-table YOUR_PROJECT.abm.signals --out ha.sql
bq query --use_legacy_sql=false --dry_run < ha.sql
bq query --use_legacy_sql=false --maximum_bytes_billed=200000000000 < ha.sql

# 4. changes and scores
bq query --use_legacy_sql=false < bigquery/20_tech_changes.sql
bq query --use_legacy_sql=false < bigquery/30_account_scores.sql
```

`30_account_scores.sql` outputs `tier_1` / `tier_2` / `tier_3`, matching HubSpot's `hs_ideal_customer_profile` values, so it can sync straight to the CRM. Read [docs/bigquery-setup.md](docs/bigquery-setup.md) before querying HTTP Archive: the tables are huge.

## n8n (optional, runs weekly by itself)

Import [`n8n/tech-footprint-weekly.json`](n8n/tech-footprint-weekly.json). It loads a compiled pack from this repo, checks each account's website and DNS (via DNS-over-HTTPS), scores, and writes to `abm.signals`. Setup: [n8n/README.md](n8n/README.md).

## Repo layout

```
footprint/            Python CLI (scan, discover, packs, compile-packs, httparchive-sql) + posture checks
collectors/           browser-collect.js and dns-collect.js, for sites or networks that block the scanner
stack-packs/          _core.yaml + industry packs + _template.yaml
stack-packs/compiled/ JSON versions of each pack (used by n8n)
bigquery/             00_schema, 10_httparchive_match (template), 20_tech_changes, 30_account_scores
n8n/                  weekly workflow JSON + readable copy of its detection code
sample-data/          sample account lists per industry (company domains only)
docs/                 how-it-works, who-benefits, stack-packs, build-a-pack-with-ai, bigquery-setup, security-and-email-checks, run-on-github
.github/workflows/    ci.yml (tests) and scan.yml (run scans on GitHub Actions)
tests/                offline tests (pytest -q)
```

## Be a good citizen

- **One page per site, politely.** The CLI waits 1 second between accounts and identifies itself with a User-Agent. Don't lower the delay for big lists.
- **Company data only.** Never commit personal contact data to a public repo. Sample data here is public company domains.
- **crt.sh and PageSpeed are shared, free services.** Cache results; don't hammer them.
- **BigQuery costs real money if you skip the filters.** Dry run, cap bytes, keep the date filter.
- **Fingerprints are a starter set.** A match is evidence, not proof. Check the `evidence` column before you put a claim in outreach.

## Roadmap

Sibling bundles writing to the same tables:

- `abm-signal-warehouse`: shared schema, fit + intent + engagement scoring, CRM write-back
- `abm-hiring-signals`: Greenhouse, Lever and Ashby public job boards
- `abm-public-company-triggers`: SEC EDGAR 8-K events, filings full-text search
- `abm-news-pulse`: GDELT news and themes per account
- `abm-activation-kit`: LinkedIn matched audiences, HubSpot, 1:1 pages

## Contributing

New fingerprints and industry packs are the most useful contributions. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. Tool names and trademarks belong to their owners; this project only detects publicly visible references to them.
