"""Command line interface.

  python -m footprint scan      --pack stack-packs/hospitality.yaml --accounts sample-data/accounts-hospitality.csv
  python -m footprint discover  example.com
  python -m footprint packs
  python -m footprint compile-packs
  python -m footprint httparchive-sql --pack stack-packs/hospitality.yaml --accounts-table myproj.abm.accounts
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from . import detect, fetch, packs, posture, signals

ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = ROOT / "stack-packs"


# ---------------------------------------------------------------- helpers
def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _read_accounts(path: str | None, domains: list[str] | None) -> list[str]:
    out: list[str] = []
    if domains:
        out += domains
    if path:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            col = next((c for c in reader.fieldnames or [] if c.strip().lower() in ("domain", "website", "company_domain", "url")), None)
            if not col:
                sys.exit(f"{path}: needs a 'domain' (or 'website') column")
            out += [row[col] for row in reader]
    clean = [detect.normalise_domain(d) for d in out]
    return list(dict.fromkeys(d for d in clean if d))


def _resolve_pack(value: str) -> Path:
    p = Path(value)
    if p.exists():
        return p
    candidate = PACK_DIR / f"{value}.yaml"
    if candidate.exists():
        return candidate
    sys.exit(f"Pack not found: {value}. Run `python -m footprint packs` to list them.")


def _latest_snapshot(snap_dir: Path, today: str) -> dict[str, set[str]] | None:
    files = sorted(p for p in snap_dir.glob("*.jsonl") if p.stem < today)
    if not files:
        return None
    prev: dict[str, set[str]] = {}
    for line in files[-1].read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        prev[rec["account_domain"]] = set(rec["tools"])
    return prev


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- commands
def _observe_live(domain: str, pack: dict, args) -> dict:
    """Collect everything for one account from the network."""
    obs = {"fetched": False, "url": None, "html": "", "headers": {}, "txt": [], "mx": [],
           "dmarc": [], "mta_sts": None, "bimi": None, "security_txt": None, "subs": {},
           "pagespeed": None, "errors": []}
    site = fetch.fetch_site(domain, pack["extra_paths"])
    obs.update(fetched=site["ok"], url=site["url"], html=site["html"], headers=site["headers"])
    obs["errors"].append(site["error"])
    if not args.no_dns:
        dns = fetch.get_dns(domain)
        obs["errors"].append(dns["error"])
        obs.update(txt=dns["txt"], mx=dns["mx"])
        if "email" in pack["posture"]:
            obs.update(fetch.get_email_dns(domain))
    if "web" in pack["posture"] and site["ok"]:
        obs["security_txt"] = fetch.fetch_security_txt(site["url"])
    if args.crtsh:
        crt = fetch.crtsh_subdomains(domain, args.new_days)
        obs["errors"].append(crt["error"])
        obs["subs"] = crt["new"]
    if args.pagespeed and site["ok"]:
        psi = fetch.pagespeed(site["url"], os.getenv("PAGESPEED_API_KEY"))
        obs["errors"].append(psi["error"])
        obs["pagespeed"] = psi["score"]
    return obs


def _load_raw(path: str, dns_path: str | None) -> dict[str, dict]:
    """Observations collected elsewhere (e.g. collectors/browser-collect.js).
    `path`: JSON array (or JSON lines) of {domain, url, html, headers, security_txt,
    txt, mx, dmarc, mta_sts, bimi}. `dns_path`: optional {domain: {txt, mx, dmarc, mta_sts, bimi}}."""
    text = Path(path).read_text(encoding="utf-8").strip()
    items = json.loads(text) if text.startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    dns = json.loads(Path(dns_path).read_text(encoding="utf-8")) if dns_path else {}
    out = {}
    for it in items:
        d = detect.normalise_domain(it.get("domain") or it.get("url", ""))
        merged = {**dns.get(d, {}), **{k: v for k, v in it.items() if v is not None}}
        out[d] = {"fetched": bool(merged.get("html")) and int(merged.get("status", 200) or 200) < 400,
                  "url": merged.get("url") or f"https://{d}/", "html": merged.get("html", ""),
                  "headers": merged.get("headers", {}), "txt": merged.get("txt", []), "mx": merged.get("mx", []),
                  "dmarc": merged.get("dmarc", []), "mta_sts": merged.get("mta_sts"), "bimi": merged.get("bimi"),
                  "security_txt": merged.get("security_txt"), "subs": merged.get("new_subdomains", {}),
                  "pagespeed": merged.get("pagespeed"), "errors": []}
    for d, rec in dns.items():
        out.setdefault(d, {"fetched": False, "url": None, "html": "", "headers": {}, "txt": rec.get("txt", []),
                           "mx": rec.get("mx", []), "dmarc": rec.get("dmarc", []), "mta_sts": rec.get("mta_sts"),
                           "bimi": rec.get("bimi"), "security_txt": None, "subs": {}, "pagespeed": None,
                           "errors": ["no website data in raw file"]})
    return out


def cmd_scan(args) -> None:
    pack = packs.load_pack(_resolve_pack(args.pack))
    raw = _load_raw(args.from_raw, args.dns_raw) if args.from_raw else None
    accounts = _read_accounts(args.accounts, args.domains) or (list(raw) if raw else [])
    if not accounts:
        sys.exit("No accounts. Pass --accounts file.csv, --domains a.com b.com, or --from-raw raw.json")
    if args.limit:
        accounts = accounts[: args.limit]

    out_dir = Path(args.out)
    snap_dir = out_dir / "snapshots" / pack["pack"]
    snap_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    previous = _latest_snapshot(snap_dir, today)

    all_rows, summaries, snapshot = [], [], []
    mode = "from raw file" if raw else "live"
    print(f"Scanning {len(accounts)} accounts with pack '{pack['pack']}' ({len(pack['tools'])} tools, {mode})")
    for i, domain in enumerate(accounts, 1):
        if raw is not None:
            obs = raw.get(domain) or {"fetched": False, "url": None, "html": "", "headers": {}, "txt": [], "mx": [],
                                      "dmarc": [], "mta_sts": None, "bimi": None, "security_txt": None,
                                      "subs": {}, "pagespeed": None, "errors": ["not in raw file"]}
        else:
            obs = _observe_live(domain, pack, args)

        hits = []
        if obs["fetched"]:
            hits += detect.detect_web(obs["html"], obs["headers"], pack["tools"], own_domain=domain)
        hits += detect.detect_dns(obs["txt"], obs["mx"], pack["tools"], obs["dmarc"])

        findings = []
        if "email" in pack["posture"] and (obs["txt"] or obs["mx"] or obs["dmarc"]):
            findings += posture.email_posture(obs["txt"], obs["mx"], obs["dmarc"], obs["mta_sts"], obs["bimi"])
        if "web" in pack["posture"] and obs["fetched"]:
            findings += posture.web_posture(obs["headers"], obs["security_txt"], obs["url"])

        prev_tools = previous.get(domain) if previous is not None else None
        rows = signals.build_signals(domain, pack, hits, obs["fetched"], obs["url"], prev_tools, obs["subs"],
                                     obs["pagespeed"], posture_findings=findings)
        summary = signals.summarise(domain, rows, obs["fetched"], obs["errors"])
        all_rows += rows
        summaries.append(summary)
        if obs["fetched"]:
            snapshot.append({"account_domain": domain, "tools": sorted({h["tool"] for h in hits})})
        flag = "ok " if obs["fetched"] else "ERR"
        print(f"  [{i}/{len(accounts)}] {flag} {domain:<35} score={summary['score']:<3} {summary['top_play']}")
        if raw is None and args.delay and i < len(accounts):
            time.sleep(args.delay)

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "signals.jsonl").open("w", encoding="utf-8") as fh:
        for r in all_rows:
            fh.write(json.dumps(r) + "\n")
    _write_csv(out_dir / "signals.csv", all_rows, signals.SIGNAL_FIELDS)
    summaries.sort(key=lambda s: -s["score"])
    _write_csv(out_dir / "accounts_summary.csv", summaries, signals.SUMMARY_FIELDS)
    with (snap_dir / f"{today}.jsonl").open("w", encoding="utf-8") as fh:
        for s in snapshot:
            fh.write(json.dumps(s) + "\n")

    print(f"\nWrote {len(all_rows)} signals for {len(summaries)} accounts to {out_dir}/")
    print("  accounts_summary.csv  one row per account, sorted by score (open in Sheets/Excel)")
    print("  signals.csv / .jsonl  every signal with evidence (load into BigQuery or your CRM)")
    if previous is None:
        print("  First run for this pack: run again next week to get tool added/removed signals.")


def cmd_discover(args) -> None:
    domain = detect.normalise_domain(args.domain)
    site = fetch.fetch_site(domain, args.path or [])
    if not site["ok"]:
        sys.exit(f"Could not load {domain}: {site['error']}")
    hosts = detect.external_hosts(site["html"], domain)
    print(f"Third-party hosts on {site['url']} ({len(hosts)}):\n")
    for host, count in sorted(hosts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>3}  {host}")
    if args.pack:
        pack = packs.load_pack(_resolve_pack(args.pack))
        hits = detect.detect_web(site["html"], site["headers"], pack["tools"], own_domain=domain)
        print(f"\nAlready recognised by pack '{pack['pack']}': " + (", ".join(h["name"] for h in hits) or "nothing"))
    print("\nTip: hosts that repeat across several customers of the same tool are that tool's fingerprint.")


def cmd_summary(args) -> None:
    """Markdown table of accounts_summary.csv (used for the GitHub Actions run summary)."""
    path = Path(args.file)
    if not path.exists():
        sys.exit(f"Not found: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cols = [("account_domain", "Account"), ("score", "Score"), ("top_play", "Top play"),
            ("competitors", "Competitors"), ("gaps", "Gaps"), ("posture_issues", "Posture issues"),
            ("changes", "Changes"), ("all_tools", "Tools found")]
    cols = [(k, label) for k, label in cols if rows and k in rows[0] and any(r.get(k) for r in rows)]
    title = args.title or f"Scan results: {path.parent.name}"
    print(f"### {title}\n")
    print(f"{len(rows)} accounts, {sum(1 for r in rows if r.get('fetched') == 'True')} websites loaded.\n")
    print("| " + " | ".join(label for _, label in cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows[: args.top]:
        cells = [(r.get(k) or "").replace("|", "/").replace("_", " ") if k not in ("account_domain", "all_tools")
                 else (r.get(k) or "").replace("|", "/") for k, _ in cols]
        cells = [c if len(c) <= 140 else c[:137] + "..." for c in cells]
        print("| " + " | ".join(cells) + " |")
    errors = [r for r in rows if r.get("errors")]
    if errors:
        print(f"\n{len(errors)} account(s) had errors; see accounts_summary.csv (errors column).")


def cmd_packs(args) -> None:
    for p in packs.list_packs(PACK_DIR):
        pk = packs.load_pack(p)
        print(f"  {pk['pack']:<22} {len(pk['tools']):>3} tools   {pk['description']}")


def cmd_compile(args) -> None:
    for p in packs.list_packs(PACK_DIR):
        out = packs.compile_pack(p, PACK_DIR / "compiled")
        print(f"  compiled {p.name} -> {out.relative_to(ROOT)}")


def cmd_httparchive_sql(args) -> None:
    pack = packs.load_pack(_resolve_pack(args.pack))
    rows = []
    for t in pack["tools"].values():
        if t.get("httparchive"):
            role = signals.role_of(t["id"], pack)
            q = lambda v: str(v).replace("\\", "\\\\").replace("'", "\\'")
            rows.append(f"    STRUCT('{q(t['httparchive'])}' AS technology, '{q(t['id'])}' AS tool_id, "
                        f"'{t['category']}' AS category, '{role}' AS role)")
    if not rows:
        sys.exit("No tools in this pack have an `httparchive` name.")
    template = (ROOT / "bigquery" / "10_httparchive_match.sql").read_text(encoding="utf-8")
    sql = (template.replace("{{ACCOUNTS_TABLE}}", args.accounts_table)
                   .replace("{{SIGNALS_TABLE}}", args.signals_table)
                   .replace("{{PACK}}", pack["pack"])
                   .replace("{{TOOL_MAP}}", ",\n".join(rows)))
    if args.out:
        Path(args.out).write_text(sql, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(sql)


def main(argv=None) -> None:
    _load_env()
    ap = argparse.ArgumentParser(prog="footprint", description="Free tech-footprint signals for ABM")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="scan accounts and write signals")
    s.add_argument("--pack", required=True, help="pack name (hospitality) or path to a .yaml")
    s.add_argument("--accounts", help="CSV with a 'domain' column")
    s.add_argument("--domains", nargs="*", help="domains on the command line")
    s.add_argument("--out", default="out", help="output folder (default: out)")
    s.add_argument("--crtsh", action="store_true", help="also check certificate logs for new subdomains (slow)")
    s.add_argument("--new-days", type=int, default=30, help="subdomain counts as new if first seen within N days")
    s.add_argument("--pagespeed", action="store_true", help="also get mobile PageSpeed score (set PAGESPEED_API_KEY)")
    s.add_argument("--no-dns", action="store_true", help="skip DNS lookups")
    s.add_argument("--delay", type=float, default=1.0, help="seconds between accounts (be polite)")
    s.add_argument("--limit", type=int, help="only scan the first N accounts")
    s.add_argument("--from-raw", help="use data collected elsewhere (collectors/browser-collect.js) instead of fetching")
    s.add_argument("--dns-raw", help="DNS records collected elsewhere (collectors/dns-collect.js), JSON keyed by domain")
    s.set_defaults(func=cmd_scan)

    d = sub.add_parser("discover", help="list third-party hosts on a site, to build new fingerprints")
    d.add_argument("domain")
    d.add_argument("--path", nargs="*", help="extra paths to include, e.g. /pricing")
    d.add_argument("--pack", help="also show which tools a pack already recognises")
    d.set_defaults(func=cmd_discover)

    sub.add_parser("packs", help="list available packs").set_defaults(func=cmd_packs)

    sm = sub.add_parser("summary", help="print accounts_summary.csv as a markdown table")
    sm.add_argument("file", nargs="?", default="out/accounts_summary.csv")
    sm.add_argument("--top", type=int, default=50, help="max rows")
    sm.add_argument("--title")
    sm.set_defaults(func=cmd_summary)
    sub.add_parser("compile-packs", help="write stack-packs/compiled/*.json for n8n").set_defaults(func=cmd_compile)

    h = sub.add_parser("httparchive-sql", help="generate the BigQuery HTTP Archive query for a pack")
    h.add_argument("--pack", required=True)
    h.add_argument("--accounts-table", default="YOUR_PROJECT.abm.accounts")
    h.add_argument("--signals-table", default="YOUR_PROJECT.abm.signals")
    h.add_argument("--out", help="write to a file instead of printing")
    h.set_defaults(func=cmd_httparchive_sql)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except packs.PackError as exc:
        sys.exit(f"Pack error: {exc}")


if __name__ == "__main__":
    main()
