"""Security and email posture checks.

Pure functions over data the collectors already gathered (DNS records and
homepage response headers). No network calls here.

Each finding: {"id", "status": "issue" | "ok" | "info", "category", "evidence"}.
Issues become scored `posture` signals; ok/info are recorded with weight 0 so
the evidence is still visible.
"""
from __future__ import annotations

import re

# default weight and play per finding id (packs can override with posture_weights / posture_plays)
DEFAULTS: dict[str, tuple[int, str]] = {
    # email authentication / deliverability
    "dmarc_missing": (30, "email_auth_rollout"),
    "dmarc_monitor_only": (20, "dmarc_enforcement"),
    "dmarc_partial_enforcement": (10, "dmarc_enforcement"),
    "dmarc_no_reporting": (5, "dmarc_enforcement"),
    "dmarc_subdomains_unprotected": (5, "dmarc_enforcement"),
    "dmarc_enforced": (0, ""),
    "spf_missing": (25, "email_auth_rollout"),
    "spf_multiple_records": (20, "email_auth_rollout"),
    "spf_permissive_all": (15, "email_auth_rollout"),
    "spf_too_many_lookups": (15, "email_auth_rollout"),
    "spf_softfail": (0, ""),
    "spf_hardfail": (0, ""),
    "mta_sts_missing": (3, "email_security_hardening"),
    "bimi_missing": (2, "brand_trust_in_inbox"),
    "bimi_present": (0, ""),
    "no_mx": (0, ""),
    # website security
    "hsts_missing": (10, "security_posture_audit"),
    "hsts_short": (3, "security_posture_audit"),
    "csp_missing": (8, "security_posture_audit"),
    "clickjacking_unprotected": (5, "security_posture_audit"),
    "nosniff_missing": (3, "security_posture_audit"),
    "referrer_policy_missing": (2, "security_posture_audit"),
    "server_version_exposed": (5, "security_posture_audit"),
    "security_txt_missing": (5, "vuln_disclosure_setup"),
    "security_txt_present": (0, ""),
    "web_headers_strong": (0, ""),
}

_SPF_LOOKUP_TERMS = re.compile(r"(?:^|\s)[+\-~?]?(include:|a(?::|/|\s|$)|mx(?::|/|\s|$)|ptr|exists:|redirect=)", re.I)


def _f(fid, status, category, evidence):
    return {"id": fid, "status": status, "category": category, "evidence": evidence}


def parse_tags(record: str) -> dict:
    tags = {}
    for part in record.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            tags[k.strip().lower()] = v.strip()
    return tags


def email_posture(root_txt: list[str], mx: list[str], dmarc_txt: list[str],
                  mta_sts_txt: list[str] | None = None, bimi_txt: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    cat = "email_auth"

    # SPF
    spf = [t.strip().strip('"') for t in root_txt or [] if t.strip().strip('"').lower().startswith("v=spf1")]
    if not spf:
        out.append(_f("spf_missing", "issue", cat, "no v=spf1 TXT record"))
    else:
        if len(spf) > 1:
            out.append(_f("spf_multiple_records", "issue", cat, f"{len(spf)} SPF records (permerror)"))
        rec = spf[0].lower()
        terms = rec.split()
        all_term = next((t for t in terms if t.lstrip("+-~?") == "all"), "")
        if all_term in ("+all", "?all", "all"):
            out.append(_f("spf_permissive_all", "issue", cat, f"SPF ends with {all_term}"))
        elif all_term == "~all":
            out.append(_f("spf_softfail", "info", cat, "SPF ~all (soft fail; fine when DMARC is enforced)"))
        elif all_term == "-all":
            out.append(_f("spf_hardfail", "ok", cat, "SPF -all"))
        lookups = len(_SPF_LOOKUP_TERMS.findall(" " + rec))
        if lookups > 10:
            out.append(_f("spf_too_many_lookups", "issue", cat, f"{lookups} top-level DNS lookups (limit 10)"))

    # DMARC
    dmarc = [t for t in dmarc_txt or [] if t.strip().strip('"').lower().startswith("v=dmarc1")]
    if not dmarc:
        out.append(_f("dmarc_missing", "issue", cat, "no _dmarc TXT record"))
    else:
        tags = parse_tags(dmarc[0])
        p = tags.get("p", "").lower()
        pct = tags.get("pct", "100")
        sp = tags.get("sp", "").lower()
        if p in ("", "none"):
            out.append(_f("dmarc_monitor_only", "issue", cat, "DMARC p=none (monitoring only, spoofed mail still delivered)"))
        else:
            if pct.isdigit() and int(pct) < 100:
                out.append(_f("dmarc_partial_enforcement", "issue", cat, f"DMARC p={p} but pct={pct}"))
            else:
                out.append(_f("dmarc_enforced", "ok", cat, f"DMARC p={p}"))
            if sp == "none":
                out.append(_f("dmarc_subdomains_unprotected", "issue", cat, "DMARC sp=none (subdomains can be spoofed)"))
        if "rua" not in tags:
            out.append(_f("dmarc_no_reporting", "issue", cat, "DMARC has no rua= reporting address"))

    if not mx:
        out.append(_f("no_mx", "info", cat, "no MX records (domain does not receive mail)"))
    if mta_sts_txt is not None and not mta_sts_txt:
        out.append(_f("mta_sts_missing", "issue", cat, "no _mta-sts TXT record"))
    if bimi_txt is not None:
        if bimi_txt:
            out.append(_f("bimi_present", "ok", cat, "BIMI record published"))
        else:
            out.append(_f("bimi_missing", "issue", cat, "no default._bimi record (no logo in inbox)"))
    return out


def web_posture(headers: dict, security_txt: bool | None, url: str | None = None) -> list[dict]:
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    out: list[dict] = []
    cat = "web_security"
    https = (url or "https://").startswith("https://")

    hsts = h.get("strict-transport-security")
    if https and hsts is None:
        out.append(_f("hsts_missing", "issue", cat, "no Strict-Transport-Security header"))
    elif hsts is not None:
        m = re.search(r"max-age=(\d+)", hsts, re.I)
        if m and int(m.group(1)) < 15552000:
            out.append(_f("hsts_short", "issue", cat, f"HSTS max-age={m.group(1)} (< 180 days)"))

    csp = h.get("content-security-policy")
    if csp is None:
        out.append(_f("csp_missing", "issue", cat, "no Content-Security-Policy header"))
    if "x-frame-options" not in h and not (csp and "frame-ancestors" in csp.lower()):
        out.append(_f("clickjacking_unprotected", "issue", cat, "no X-Frame-Options or CSP frame-ancestors"))
    if h.get("x-content-type-options", "").lower() != "nosniff":
        out.append(_f("nosniff_missing", "issue", cat, "no X-Content-Type-Options: nosniff"))
    if "referrer-policy" not in h:
        out.append(_f("referrer_policy_missing", "issue", cat, "no Referrer-Policy header"))
    server = h.get("server", "") + " " + h.get("x-powered-by", "")
    if re.search(r"/\d+(\.\d+)+", server):
        out.append(_f("server_version_exposed", "issue", cat, f"version in headers: {server.strip()}"))
    if not any(f["status"] == "issue" for f in out):
        out.append(_f("web_headers_strong", "ok", cat, "HSTS, CSP, clickjacking, nosniff and referrer policy all set"))

    if security_txt is not None:
        out.append(_f("security_txt_present", "ok", cat, "/.well-known/security.txt") if security_txt
                   else _f("security_txt_missing", "issue", cat, "no /.well-known/security.txt (RFC 9116)"))
    return out


def weight_and_play(fid: str, pack: dict) -> tuple[int, str]:
    w, play = DEFAULTS.get(fid, (0, ""))
    w = pack.get("posture_weights", {}).get(fid, w)
    play = pack.get("posture_plays", {}).get(fid, play)
    return int(w), play
