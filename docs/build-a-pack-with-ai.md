# Draft a pack for any industry with an AI assistant

Paste the prompt below into Claude (or any assistant with web search), fill in the three brackets, and save the answer as `stack-packs/<industry>.yaml`. Then **verify every pattern with `discover`** on two or three real customers of each tool before trusting it: AI drafts are a starting point, not evidence.

---

```text
You are helping me build a "stack pack" for the open-source repo abm-tech-footprint.
It detects which tools a company uses from public signals only: website HTML
(script/link/iframe hosts), HTTP headers, DNS TXT/SPF/MX records.

Industry: [e.g. property management / multifamily housing]
What I sell: [one line]
My main competitors (products): [list]

Produce a YAML file in exactly this format (see stack-packs/_template.yaml):

pack, description, extends: [_core], version: 1
seller: product, competitors, complements, must_have_categories
plays: competitor_found, complement_found, gap_found, tool_added,
       competitor_removed, subdomain_new, slow_site
interesting_subdomains, extra_paths
tools: 10 to 25 tools common in this industry that are VISIBLE on a website or
       in DNS. For each: name, category, patterns (html / headers / dns_txt / spf / mx).

Rules:
- Only include tools that load something publicly visible (a script, widget,
  iframe, link to a hosted portal, DNS record). Skip pure back-office software.
- Patterns must be specific hosts or strings the tool's embed actually uses
  (e.g. "widget.vendor.com"), not generic words. Give 1 to 3 per tool.
- Mark any pattern you are not sure about with a YAML comment "# verify".
- Do not repeat tools already in _core (Google Analytics, GTM, HubSpot,
  Intercom, Drift, WordPress, Shopify, Cloudflare, Google Workspace, etc.).
- Use only tool ids from the `tools` block in seller.competitors / complements.
- must_have_categories must be categories used by at least one tool.
After the YAML, list which 3 to 5 public customer websites I should run
`python -m footprint discover` on to verify the most important patterns.
```

---

Then:

```bash
python -m footprint packs                 # validates the new file
python -m footprint discover <customer>.com --pack <industry>
python -m footprint scan --pack <industry> --domains a.com b.com --delay 0
```

Remove anything marked `# verify` that you couldn't confirm. Open a PR if it works well, so other marketers in that industry can use it.
