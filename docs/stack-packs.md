# Stack packs

A stack pack is one YAML file that tells the scanner, for one industry:

1. **which tools to look for** and how to recognise them (fingerprints)
2. **what you sell** (which tools are competitors, which are complements, which categories should exist)
3. **what to do** about each signal (plays and weights)

Every pack extends `_core.yaml`, which carries about 60 cross-industry tools (CMS, analytics, chat, email provider, SaaS verification tokens and more).

## Fields

```yaml
pack: hospitality            # id, used in output and file names
description: Hotels and resorts
extends: [_core]             # inherit tools, weights, subdomains from other packs
version: 1

seller:
  product: "What you sell"
  competitors: [asksuite]     # tool ids you replace           -> role=competitor
  complements: [synxis]       # tool ids you integrate with    -> role=complement
  must_have_categories: [chat]  # missing category             -> gap signal

plays:                        # label per signal type; map these to your sequences
  competitor_found: displacement_sequence
  complement_found: integration_pitch
  gap_found: revenue_leak_audit
  tool_added: timing_trigger
  tool_removed: timing_trigger
  competitor_removed: switch_window_outreach
  subdomain_new: launch_congrats_touch
  slow_site: speed_audit

weights:                      # optional, overrides _core
  competitor_found: 40

interesting_subdomains: [book, events]   # only these become subdomain_new signals
extra_paths: ["/meetings"]               # extra pages to fetch besides the homepage

tools:
  synxis:                                 # tool id: lowercase, underscores
    name: SynXis Booking Engine (Sabre)   # shown in outputs
    category: booking_engine              # used for gaps and grouping
    patterns:
      html: ["synxis.com"]                # substrings in page HTML (host-boundary aware)
      headers: {"server": "cloudflare"}   # header name -> substring ("" = header present)
      dns_txt: ["atlassian-domain-verification"]
      spf: ["sendgrid.net"]
      mx: ["pphosted.com"]
    httparchive: SynXis                   # optional: exact HTTP Archive technology name
```

Patterns are case-insensitive. Prefix with `re:` for a regular expression, for example `"re:^ms=ms\\d+"`.

A tool defined in a pack with the same id as one in `_core` replaces it.

## Building fingerprints with `discover`

You rarely need to guess. Find a few companies you know use a tool (case studies, customer logos pages, "powered by" footers), then:

```bash
python -m footprint discover knowncustomer1.com --pack hospitality
python -m footprint discover knowncustomer2.com --pack hospitality --path /book
```

Output lists every third-party host on the page with a count, and what the pack already recognises. The host that shows up on every customer of the tool (and not on non-customers) is the fingerprint. Prefer:

- the vendor's **script or widget host** (`widget.vendor.com`, `cdn.vendor.io`) over its marketing domain
- **two or more** patterns per tool when the vendor uses several hosts
- **specific** strings over generic words (`mktoforms2`, not `forms`)

Then check a couple of non-customers to make sure the pattern doesn't fire there too.

## Test a pack

```bash
python -m footprint packs                                   # validates every pack
python -m footprint scan --pack my-industry --domains a.com b.com c.com --delay 0
python -m footprint compile-packs                           # refresh JSON for n8n
pytest -q
```

`packs` fails loudly if `seller` lists a tool id or category that doesn't exist, which catches most typos.

## Finding HTTP Archive names

To use a tool in the BigQuery match, set `httparchive:` to the exact technology name HTTP Archive uses. You can list names cheaply with a small, filtered query:

```sql
SELECT t.technology, COUNT(*) AS sites
FROM `httparchive.crawl.pages` TABLESAMPLE SYSTEM (0.1 PERCENT), UNNEST(technologies) t
WHERE date = '2026-09-01' AND client = 'mobile' AND is_root_page
  AND LOWER(t.technology) LIKE '%booking%'
GROUP BY 1 ORDER BY 2 DESC;
```

Dry run it first and set `--maximum_bytes_billed` (see [bigquery-setup.md](bigquery-setup.md)).
