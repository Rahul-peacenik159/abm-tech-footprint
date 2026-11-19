"""Turn detections into scored signal rows and a one-row-per-account summary.

Signal row schema (same columns as bigquery/00_schema.sql -> signals):
  account_domain, signal_type, signal_value, tool_name, category, role,
  weight, play, source, evidence, evidence_url, pack, observed_at
"""
from __future__ import annotations

from datetime import datetime, timezone

SIGNAL_FIELDS = [
    "account_domain", "signal_type", "signal_value", "tool_name", "category", "role",
    "weight", "play", "source", "evidence", "evidence_url", "pack", "observed_at",
]
SUMMARY_FIELDS = [
    "account_domain", "fetched", "score", "top_play", "competitors", "complements",
    "gaps", "changes", "new_subdomains", "pagespeed_mobile", "all_tools", "errors",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def role_of(tool_id: str, pack: dict) -> str:
    seller = pack["seller"]
    if tool_id in seller.get("competitors", []):
        return "competitor"
    if tool_id in seller.get("complements", []):
        return "complement"
    return "neutral"


def _row(domain, pack, observed_at, **kw) -> dict:
    row = {f: "" for f in SIGNAL_FIELDS}
    row.update(account_domain=domain, pack=pack["pack"], observed_at=observed_at, weight=0)
    row.update(kw)
    return row


def build_signals(domain: str, pack: dict, hits: list[dict], fetched: bool, page_url: str | None,
                  previous_tools: set[str] | None = None, new_subdomains: dict | None = None,
                  pagespeed_score: int | None = None, slow_threshold: int = 50,
                  observed_at: str | None = None) -> list[dict]:
    observed_at = observed_at or now_iso()
    w, plays = pack["weights"], pack["plays"]
    rows: list[dict] = []

    # 1. Every tool found
    found = {}
    for h in hits:
        if h["tool"] in found:
            continue
        found[h["tool"]] = h
        role = role_of(h["tool"], pack)
        key = {"competitor": "competitor_found", "complement": "complement_found"}.get(role)
        rows.append(_row(domain, pack, observed_at,
                         signal_type="tech_detected", signal_value=h["tool"], tool_name=h["name"],
                         category=h["category"], role=role, weight=w.get(key, 0) if key else 0,
                         play=plays.get(key, "") if key else "", source=h["source"],
                         evidence=h["evidence"], evidence_url=page_url or ""))

    # 2. Gaps: a must-have category with nothing in it (only if the site loaded)
    if fetched:
        cats = {h["category"] for h in found.values()}
        for cat in pack["seller"].get("must_have_categories", []):
            if cat not in cats:
                rows.append(_row(domain, pack, observed_at, signal_type="gap", signal_value=cat,
                                 category=cat, role="gap", weight=w.get("gap_found", 0),
                                 play=plays.get("gap_found", ""), source="homepage",
                                 evidence=f"no {cat} tool detected", evidence_url=page_url or ""))

    # 3. Changes vs the previous snapshot
    if previous_tools is not None and fetched:
        tools = pack["tools"]
        for t in sorted(set(found) - previous_tools):
            rows.append(_row(domain, pack, observed_at, signal_type="tech_added", signal_value=t,
                             tool_name=found[t]["name"], category=found[t]["category"],
                             role=role_of(t, pack), weight=w.get("tool_added", 0),
                             play=plays.get("tool_added", ""), source="snapshot_diff",
                             evidence="not seen in previous scan", evidence_url=page_url or ""))
        for t in sorted(previous_tools - set(found)):
            if t not in tools:
                continue
            role = role_of(t, pack)
            key = "competitor_removed" if role == "competitor" else "tool_removed"
            rows.append(_row(domain, pack, observed_at, signal_type="tech_removed", signal_value=t,
                             tool_name=tools[t]["name"], category=tools[t]["category"], role=role,
                             weight=w.get(key, 0), play=plays.get(key, ""), source="snapshot_diff",
                             evidence="seen in previous scan, missing now", evidence_url=page_url or ""))

    # 4. New interesting subdomains (certificate logs)
    interesting = set(pack.get("interesting_subdomains", []))
    for sub, first_seen in sorted((new_subdomains or {}).items()):
        label = sub[: -(len(domain) + 1)].split(".")[-1]
        if label in interesting:
            rows.append(_row(domain, pack, observed_at, signal_type="subdomain_new", signal_value=sub,
                             category="subdomain", role="neutral", weight=w.get("subdomain_new", 0),
                             play=plays.get("subdomain_new", ""), source="crtsh",
                             evidence=f"first certificate {first_seen}",
                             evidence_url=f"https://crt.sh/?q={sub}"))

    # 5. Site speed
    if pagespeed_score is not None:
        slow = pagespeed_score < slow_threshold
        rows.append(_row(domain, pack, observed_at, signal_type="pagespeed_mobile", signal_value=str(pagespeed_score),
                         category="site_performance", role="gap" if slow else "neutral",
                         weight=w.get("slow_site", 0) if slow else 0,
                         play=plays.get("slow_site", "") if slow else "", source="pagespeed",
                         evidence=f"mobile performance score {pagespeed_score}/100",
                         evidence_url=page_url or ""))
    return rows


def summarise(domain: str, rows: list[dict], fetched: bool, errors: list[str]) -> dict:
    def names(pred):
        return "; ".join(sorted({r["tool_name"] or r["signal_value"] for r in rows if pred(r)}))

    scored = sorted((r for r in rows if r["weight"]), key=lambda r: -int(r["weight"]))
    score = min(100, sum(int(r["weight"]) for r in scored))
    speed = next((r["signal_value"] for r in rows if r["signal_type"] == "pagespeed_mobile"), "")
    return {
        "account_domain": domain,
        "fetched": fetched,
        "score": score,
        "top_play": scored[0]["play"] if scored else "",
        "competitors": names(lambda r: r["signal_type"] == "tech_detected" and r["role"] == "competitor"),
        "complements": names(lambda r: r["signal_type"] == "tech_detected" and r["role"] == "complement"),
        "gaps": names(lambda r: r["signal_type"] == "gap"),
        "changes": "; ".join(f"{'+' if r['signal_type'] == 'tech_added' else '-'}{r['tool_name']}"
                             for r in rows if r["signal_type"] in ("tech_added", "tech_removed")),
        "new_subdomains": names(lambda r: r["signal_type"] == "subdomain_new"),
        "pagespeed_mobile": speed,
        "all_tools": names(lambda r: r["signal_type"] == "tech_detected"),
        "errors": " | ".join(e for e in errors if e),
    }
