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

from . import detect, fetch, packs, signals

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
def cmd_scan(args) -> None:
    pack = packs.load_pack(_resolve_pack(args.pack))
    accounts = _read_accounts(args.accounts, args.domains)
    if not accounts:
        sys.exit("No accounts. Pass --accounts file.csv or --domains a.com b.com")
    if args.limit:
        accounts = accounts[: args.limit]

    out_dir = Path(args.out)
    snap_dir = out_dir / "snapshots" / pack["pack"]
    snap_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    previous = _latest_snapshot(snap_dir, today)
    psi_key = os.getenv("PAGESPEED_API_KEY")

    all_rows, summaries, snapshot = [], [], []
    print(f"Scanning {len(accounts)} accounts with pack '{pack['pack']}' ({len(pack['tools'])} tools)")
    for i, domain in enumerate(accounts, 1):
        errors, hits = [], []
        site = fetch.fetch_site(domain, pack["extra_paths"])
        errors.append(site["error"])
        if site["ok"]:
            hits += detect.detect_web(site["html"], site["headers"], pack["tools"], own_domain=domain)
        if not args.no_dns:
            dns = fetch.get_dns(domain)
            errors.append(dns["error"])
            hits += detect.detect_dns(dns["txt"], dns["mx"], pack["tools"])
        subs = {}
        if args.crtsh:
            crt = fetch.crtsh_subdomains(domain, args.new_days)
            errors.append(crt["error"])
            subs = crt["new"]
        score = None
        if args.pagespeed and site["ok"]:
            psi = fetch.pagespeed(site["url"], psi_key)
            errors.append(psi["error"])
            score = psi["score"]

        prev_tools = previous.get(domain) if previous is not None else None
        rows = signals.build_signals(domain, pack, hits, site["ok"], site["url"], prev_tools, subs, score)
        summary = signals.summarise(domain, rows, site["ok"], errors)
        all_rows += rows
        summaries.append(summary)
        if site["ok"]:
            snapshot.append({"account_domain": domain, "tools": sorted({h["tool"] for h in hits})})
        flag = "ok " if site["ok"] else "ERR"
        print(f"  [{i}/{len(accounts)}] {flag} {domain:<35} score={summary['score']:<3} {summary['top_play']}")
        if args.delay and i < len(accounts):
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
    s.set_defaults(func=cmd_scan)

    d = sub.add_parser("discover", help="list third-party hosts on a site, to build new fingerprints")
    d.add_argument("domain")
    d.add_argument("--path", nargs="*", help="extra paths to include, e.g. /pricing")
    d.add_argument("--pack", help="also show which tools a pack already recognises")
    d.set_defaults(func=cmd_discover)

    sub.add_parser("packs", help="list available packs").set_defaults(func=cmd_packs)
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
