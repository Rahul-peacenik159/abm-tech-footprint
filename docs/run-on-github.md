# Run scans on GitHub (no laptop, no installs)

The `scan` workflow (`.github/workflows/scan.yml`) runs the scanner on GitHub's own servers with GitHub Actions. You click a button, pick a pack and an account list, and get a results table plus downloadable CSVs. GitHub's servers have open internet access, so live website, DNS and certificate checks all work.

## Run it

1. Open the repo on GitHub and click the **Actions** tab.
2. In the left sidebar, click **scan**.
3. Click **Run workflow** (right side) and fill in:
   - **Stack pack:** for example `security-compliance` or `email-deliverability`
   - **Account list CSV:** a file in the repo with a `domain` column, e.g. `sample-data/accounts-enterprise-startups.csv`
   - **Or type domains:** `acme.com example.io` (overrides the CSV)
   - **render** (on by default): opens each site in a real headless browser, so tools that load through Google Tag Manager or after the page starts (cookie banners, ad pixels, chat widgets) are found. Adds about 1 minute. Turn it off for a quicker, rougher scan.
   - **crtsh / pagespeed:** optional extra checks (slower)
4. Click the green **Run workflow** button. A run appears in the list after a few seconds; it takes 1 to 3 minutes for 10 accounts.
5. Open the run:
   - **Summary** page: results table, one row per account, sorted by score.
   - **Artifacts** (bottom of the Summary page): `scan-results-<pack>` zip with `accounts_summary.csv`, `signals.csv`, `signals.jsonl`. Open the CSVs in Google Sheets or Excel.

Run both security packs on the same list by running the workflow twice, once per pack.

## Use your own account list

Add a CSV with a `domain` column to the repo (for example `targets/my-accounts.csv`) and type its path in **Account list CSV**. Or paste the domains into the **domains** box.

**Keep real prospect lists out of a public repo.** In a public repo, anyone can see the files, the run logs, the summary table and the artifacts. For your real targets:

1. Create a **private** repo: on GitHub, **+ > Import repository**, paste this repo's URL, and set visibility to **Private**. (Or use "Use this template" if enabled.) A fork of a public repo can't be made private, so import instead.
2. Put your account lists in the private copy and run the workflow there.
3. Pull improvements from the public repo whenever you like:
   ```bash
   git remote add upstream https://github.com/Rahul-peacenik159/abm-tech-footprint.git
   git pull upstream main
   ```

Private repos use your account's free monthly Actions minutes (2,000 minutes on GitHub Free at the time of writing); a 10-account scan uses about 2. Public repos run free.

## Re-running and "changes"

Every run saves a snapshot of the tools it found (kept in the Actions cache) and compares with the previous run of the same pack. The Summary page says which earlier scan it compared with and how many tools were added or removed; the **Changes** column lists them (`+Tool` added, `-Tool` removed).

Re-running a few minutes later normally shows **0 changes**: websites rarely change that fast. The useful comparison is week to week.

The first run with **render** on will list tools such as cookie banners and pixels as "added", because the earlier non-rendered scan could not see them. Ignore that one-off jump.

## Run it every week automatically

Tool **added / removed** signals need two runs to compare. To scan on a schedule:

1. In `.github/workflows/scan.yml`, uncomment the `schedule:` block (default: Mondays 03:17 UTC).
2. Scheduled runs use the defaults in the `env:` block: change `security-compliance` and `sample-data/accounts-enterprise-startups.csv` there to your pack and list.
3. Commit. Each run restores the previous run's snapshots from the Actions cache, so the summary shows changes since last week. (GitHub deletes cache entries unused for 7 days, so keep the schedule weekly or more often.)

GitHub pauses scheduled workflows in public repos after 60 days without repo activity; any commit re-enables them.

## Optional: PageSpeed API key

For more than a handful of PageSpeed checks, create a free key in Google Cloud (APIs & Services > Credentials, enable "PageSpeed Insights API") and add it under **Settings > Secrets and variables > Actions > New repository secret** named `PAGESPEED_API_KEY`.

## From the command line

With the GitHub CLI installed and logged in:

```bash
gh workflow run scan.yml -f pack=email-deliverability -f accounts=sample-data/accounts-enterprise-startups.csv
gh run watch                           # follow progress
gh run download --name scan-results-email-deliverability   # get the CSVs
```
