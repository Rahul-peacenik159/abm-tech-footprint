"""Pure matching logic: no network calls here, so it is easy to test."""
from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

_HOSTLIKE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}(/.*)?$")
_URL_ATTR = re.compile(r"""(?:src|href|data-src|action)\s*=\s*["']([^"']+)["']""", re.I)
_BARE_URL = re.compile(r"""https?://([a-z0-9.-]+\.[a-z]{2,})""", re.I)


def normalise_domain(value: str) -> str:
    """'https://www.Example.com/path' -> 'example.com'"""
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "http://" + value
    host = urlparse(value).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _compile(pattern: str):
    """Substring patterns that look like hosts must start at a host boundary,
    so 'olo.com' does not match 'polo.com'. 're:' patterns are regexes."""
    if pattern.startswith("re:"):
        return re.compile(pattern[3:], re.I)
    if _HOSTLIKE.match(pattern):
        return re.compile(r"(?<![a-z0-9-])" + re.escape(pattern))
    return re.compile(re.escape(pattern))


_CACHE: dict[str, re.Pattern] = {}


def _match(pattern: str, text: str) -> bool:
    rx = _CACHE.get(pattern)
    if rx is None:
        rx = _CACHE[pattern] = _compile(pattern)
    return bool(rx.search(text))


def _is_own(pattern: str, own_domain: str) -> bool:
    """Skip patterns that point at the account's own domain (e.g. scanning a vendor)."""
    if not own_domain or not _HOSTLIKE.match(pattern):
        return False
    host = pattern.split("/")[0]
    return host == own_domain or host.endswith("." + own_domain)


def detect_web(html: str, headers: dict, tools: dict, own_domain: str = "") -> list[dict]:
    """Return one hit per tool found in page HTML or response headers."""
    html_l = (html or "").lower()
    headers_l = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    hits = []
    for tool in tools.values():
        pats = tool["patterns"]
        evidence = None
        for p in pats.get("html", []):
            if not _is_own(p, own_domain) and _match(p, html_l):
                evidence = ("homepage", p)
                break
        if evidence is None:
            for name, needle in pats.get("headers", {}).items():
                if name in headers_l and (needle == "" or needle in headers_l[name]):
                    evidence = ("headers", f"{name}: {needle or '(present)'}")
                    break
        if evidence:
            hits.append(_hit(tool, *evidence))
    return hits


def detect_dns(txt_records: list[str], mx_records: list[str], tools: dict) -> list[dict]:
    """Return one hit per tool found in TXT, SPF or MX records."""
    txt_l = [t.lower().strip('"') for t in txt_records or []]
    spf_l = [t for t in txt_l if t.startswith("v=spf1")]
    other_txt = [t for t in txt_l if not t.startswith("v=spf1")]
    mx_l = [m.lower().rstrip(".") for m in mx_records or []]
    hits = []
    for tool in tools.values():
        pats = tool["patterns"]
        evidence = None
        for source, records, key in (("dns_txt", other_txt, "dns_txt"), ("spf", spf_l, "spf"), ("dns_mx", mx_l, "mx")):
            for p in pats.get(key, []):
                if any(_match(p, r) for r in records):
                    evidence = (source, p)
                    break
            if evidence:
                break
        if evidence:
            hits.append(_hit(tool, *evidence))
    return hits


def _hit(tool: dict, source: str, evidence: str) -> dict:
    return {"tool": tool["id"], "name": tool["name"], "category": tool["category"], "source": source, "evidence": evidence}


def external_hosts(html: str, own_domain: str) -> Counter:
    """Every third-party host referenced by the page, with counts (for `discover`)."""
    hosts: Counter = Counter()
    for url in _URL_ATTR.findall(html or ""):
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http"):
            host = (urlparse(url).hostname or "").lower()
            if host:
                hosts[host] += 1
    for host in _BARE_URL.findall(html or ""):
        hosts[host.lower()] += 0  # seen in inline code; keep it listed
    own = normalise_domain(own_domain)
    return Counter({h: c for h, c in hosts.items() if not (h == own or h.endswith("." + own))})
