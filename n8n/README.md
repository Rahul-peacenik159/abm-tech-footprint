# n8n workflow: ABM tech footprint (weekly)

`tech-footprint-weekly.json` runs every Monday at 7am (and on demand) with no code to host.

```
Manual run / Every Monday 7am
  -> Load stack pack       (compiled JSON from this repo, e.g. stack-packs/compiled/hospitality.json)
  -> Accounts              (replace with Google Sheets / BigQuery / HubSpot node with a `domain` field)
  -> Fetch homepage        (HTTP, full response as text, continues on error)
  -> DNS TXT, DNS MX       (DNS-over-HTTPS via dns.google)
  -> Detect tools and score (Code node, same logic as the Python CLI)
  -> Write to BigQuery abm.signals
```

## Setup

1. In n8n: **Workflows > Import from file** and pick `tech-footprint-weekly.json`.
2. **Load stack pack:** change the file name at the end of the URL to the pack you want. To use your own edited pack, fork this repo, run `python -m footprint compile-packs`, push, and point the URL at your fork.
3. **Accounts:** swap the Code node for a node that reads your list (Google Sheets, BigQuery `SELECT domain FROM abm.accounts`, or a HubSpot company search). Each item needs a `domain` field.
4. **Write to BigQuery:** add a Google BigQuery credential, then select your project, dataset `abm` and table `signals` (create them with `bigquery/00_schema.sql`). If the node shows a warning after import, re-select the three fields. Prefer Sheets? Replace it with a Google Sheets "Append row" node; the columns are the same.
5. Run it once with **Manual run** on 3 to 5 domains, check the output of **Detect tools and score**, then activate the workflow.

## Notes

- The Code node copy lives in `detect-node.js` for easy reading and diffs. If you change one, paste it into the other.
- The n8n version covers website, headers and DNS. Certificate logs (crt.sh), PageSpeed and tool added/removed history are handled by the Python CLI and `bigquery/20_tech_changes.sql`.
- Rows with `signal_type = fetch_error` mean the website did not load (blocked, down or wrong domain). They have weight 0.
- For large lists, add a **Loop Over Items** node with a batch size of 10 and a **Wait** node of a few seconds between batches to stay polite.
