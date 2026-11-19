# Security, CDN, compliance and email checks

Two packs turn on **posture checks**: tests of how well a company has set up its website security and email authentication, using public data only. They are built for anyone selling security, compliance, infrastructure, email security or deliverability, especially into startups that sell to enterprises. Those startups get security questionnaires from their first big customer, usually before they have a security team.

```bash
python -m footprint scan --pack security-compliance  --domains a.com b.com
python -m footprint scan --pack email-deliverability --domains a.com b.com
```

Posture findings appear as `signal_type = posture` rows (with the evidence) and in the `posture_issues` column of `accounts_summary.csv`.

## `security-compliance` pack (`posture: [web]`)

| Check | Source | Finding ids |
|---|---|---|
| HSTS | `Strict-Transport-Security` header | `hsts_missing`, `hsts_short` (< 180 days) |
| Content Security Policy | `Content-Security-Policy` | `csp_missing` |
| Clickjacking | `X-Frame-Options` or CSP `frame-ancestors` | `clickjacking_unprotected` |
| MIME sniffing | `X-Content-Type-Options: nosniff` | `nosniff_missing` |
| Referrer policy | `Referrer-Policy` | `referrer_policy_missing` |
| Version leak | `Server` / `X-Powered-By` with a version number | `server_version_exposed` |
| Vulnerability disclosure | `/.well-known/security.txt` (RFC 9116) | `security_txt_missing` |

Plus tool detection for: **trust centers** (own `trust.` subdomain or `/trust` page, Vanta, Drata, Secureframe, SafeBase, Sprinto, Conveyor, Whistic), **compliance claims** in page text (SOC 2, ISO 27001, ISO 42001, HIPAA, FedRAMP), **status pages**, **CDN/WAF/hosting** from response headers (Cloudflare, Fastly, Akamai, CloudFront, Azure Front Door, Google Cloud, Vercel, Netlify, Fly.io, Render, Webflow, Framer), **bot protection** (Turnstile, reCAPTCHA, hCaptcha) and **consent managers** (OneTrust, Cookiebot, Osano, Termly, iubenda, Usercentrics, CookieYes, HubSpot banner).

Default gaps (`seller.must_have_categories`): `trust_center`, `consent`.

## `email-deliverability` pack (`posture: [email]`)

| Check | Record | Finding ids |
|---|---|---|
| SPF exists and is valid | TXT `v=spf1` | `spf_missing`, `spf_multiple_records`, `spf_permissive_all` (`+all`/`?all`), `spf_too_many_lookups` (> 10 top-level), info: `spf_softfail`, ok: `spf_hardfail` |
| DMARC policy | TXT `_dmarc.<domain>` | `dmarc_missing`, `dmarc_monitor_only` (`p=none`), `dmarc_partial_enforcement` (`pct` < 100), `dmarc_subdomains_unprotected` (`sp=none`), `dmarc_no_reporting` (no `rua`), ok: `dmarc_enforced` |
| MTA-STS | TXT `_mta-sts.<domain>` | `mta_sts_missing` |
| BIMI | TXT `default._bimi.<domain>` | `bimi_missing`, ok: `bimi_present` |
| Receives mail | MX | info: `no_mx` |

Plus tool detection for: mailbox providers and secure email gateways (MX), sending services (SPF), and **DMARC reporting vendors** read from the DMARC `rua=` address (Valimail, dmarcian, EasyDMARC, Red Sift, PowerDMARC, Proofpoint EFD, Agari, URIports, Cloudflare, Postmark, Brevo, GoDaddy).

Why it matters for outreach: Google and Yahoo have required SPF, DKIM and a DMARC record from bulk senders since 2024. `p=none` means spoofed mail from the domain is still delivered. These are facts a prospect can check in a minute, which makes them strong openers.

DKIM is not checked: it needs the selector name, which is not public.

## Weights and plays

Defaults live in `footprint/posture.py` (`DEFAULTS`). Override per pack:

```yaml
posture_weights:
  dmarc_monitor_only: 30
  csp_missing: 0          # ignore this one
posture_plays:
  dmarc_monitor_only: dmarc_enforcement_sequence
```

## When a site blocks the scanner or your network can't reach it

Some sites block non-browser requests, and some networks (corporate proxies, sandboxes) block outbound requests. Collect in your own browser instead:

1. Open the homepage, open DevTools > Console, paste `collectors/browser-collect.js`. Save the printed JSON objects into one JSON array, `raw.json`.
2. Open `https://dns.google`, paste `collectors/dns-collect.js` with your domains filled in. Save the output as `dns.json`.
3. Run any pack offline:

```bash
python -m footprint scan --pack security-compliance  --from-raw raw.json --dns-raw dns.json
python -m footprint scan --pack email-deliverability --from-raw raw.json --dns-raw dns.json
```

The browser collector also sees scripts injected by tag managers after the page loads, which a plain HTTP fetch misses.

## Reading the results responsibly

- These are **public configuration facts**, not vulnerabilities. Say "your DMARC policy is set to monitor only", not "you're insecure".
- Headers can differ between the homepage and the product. The checks cover the marketing site only.
- A `trust.` subdomain or SOC 2 mention is a claim on the website, not a verified report.
- Never probe beyond a normal page load and public DNS. No port scans, no login attempts, no vulnerability testing.
