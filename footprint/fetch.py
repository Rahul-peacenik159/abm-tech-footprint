"""Network collectors. Every function fails soft and returns an error string
instead of raising, so one bad domain never stops a batch."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

USER_AGENT = os.getenv(
    "FOOTPRINT_USER_AGENT",
    "abm-tech-footprint/0.1 (+https://github.com/Rahul-peacenik159/abm-tech-footprint)",
)
TIMEOUT = float(os.getenv("FOOTPRINT_TIMEOUT", "20"))

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})


def fetch_site(domain: str, extra_paths: list[str] | None = None) -> dict:
    """Fetch the homepage (https, then https://www.) plus optional extra paths.
    Returns {'ok', 'url', 'html', 'headers', 'error'}; html is all pages joined."""
    result = {"ok": False, "url": None, "html": "", "headers": {}, "error": None}
    for base in (f"https://{domain}", f"https://www.{domain}"):
        try:
            r = _session.get(base, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code < 400 and r.text:
                result.update(ok=True, url=r.url, html=r.text, headers=dict(r.headers))
                break
            result["error"] = f"HTTP {r.status_code} from {base}"
        except requests.RequestException as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"[:300]
    if result["ok"]:
        root = result["url"].split("/", 3)[:3]
        root_url = "/".join(root)
        for path in extra_paths or []:
            try:
                r = _session.get(root_url + path, timeout=TIMEOUT)
                if r.status_code < 400:
                    result["html"] += "\n" + r.text
            except requests.RequestException:
                pass
        result["error"] = None
    return result


def _doh(name: str, rtype: str) -> list[str]:
    url = os.getenv("FOOTPRINT_DOH_URL", "https://dns.google/resolve")
    r = _session.get(url, params={"name": name, "type": rtype}, timeout=TIMEOUT,
                     headers={"Accept": "application/dns-json"})
    r.raise_for_status()
    answers = r.json().get("Answer", []) or []
    type_code = {"TXT": 16, "MX": 15}[rtype]
    out = []
    for a in answers:
        if a.get("type") != type_code:
            continue
        data = a.get("data", "")
        if rtype == "MX":
            data = data.split()[-1]
        else:
            data = data.replace('" "', "").strip('"')
        out.append(data)
    return out


def _txt(name: str) -> list[str]:
    try:
        import dns.resolver  # type: ignore

        try:
            return [b"".join(r.strings).decode("utf-8", "ignore") for r in dns.resolver.resolve(name, "TXT")]
        except Exception:
            return []
    except ImportError:
        try:
            return _doh(name, "TXT")
        except Exception:
            return []


def get_email_dns(domain: str) -> dict:
    """DMARC, MTA-STS and BIMI TXT records (for email posture checks)."""
    return {"dmarc": _txt(f"_dmarc.{domain}"), "mta_sts": _txt(f"_mta-sts.{domain}"),
            "bimi": _txt(f"default._bimi.{domain}")}


def fetch_security_txt(base_url: str) -> bool:
    """True when /.well-known/security.txt exists and looks like RFC 9116 text."""
    root = "/".join(base_url.split("/", 3)[:3])
    try:
        r = _session.get(root + "/.well-known/security.txt", timeout=TIMEOUT)
        body = r.text[:600].lower() if r.status_code < 400 else ""
        return "contact:" in body and "<html" not in body
    except requests.RequestException:
        return False


def get_dns(domain: str) -> dict:
    """TXT and MX records. Uses dnspython if installed, else DNS-over-HTTPS."""
    result = {"txt": [], "mx": [], "error": None}
    try:
        import dns.resolver  # type: ignore

        try:
            result["txt"] = [b"".join(r.strings).decode("utf-8", "ignore") for r in dns.resolver.resolve(domain, "TXT")]
        except Exception:  # NXDOMAIN / NoAnswer are normal
            pass
        try:
            result["mx"] = [str(r.exchange).rstrip(".") for r in dns.resolver.resolve(domain, "MX")]
        except Exception:
            pass
        if result["txt"] or result["mx"]:
            return result
    except ImportError:
        pass
    try:
        result["txt"] = _doh(domain, "TXT")
        result["mx"] = _doh(domain, "MX")
    except Exception as exc:
        result["error"] = f"DNS lookup failed: {exc}"[:300]
    return result


def crtsh_subdomains(domain: str, since_days: int = 30) -> dict:
    """Subdomains whose first certificate appeared in the last `since_days`."""
    result = {"new": {}, "all": set(), "error": None}
    try:
        r = _session.get("https://crt.sh/", params={"q": f"%.{domain}", "output": "json"}, timeout=max(TIMEOUT, 60))
        r.raise_for_status()
        rows = r.json()
    except Exception as exc:
        result["error"] = f"crt.sh failed: {exc}"[:300]
        return result
    first_seen: dict[str, datetime] = {}
    for row in rows:
        try:
            seen = datetime.fromisoformat(row["not_before"].replace("Z", "")).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        for name in str(row.get("name_value", "")).lower().split("\n"):
            name = name.strip().lstrip("*.")
            if name.endswith("." + domain) and name != domain:
                if name not in first_seen or seen < first_seen[name]:
                    first_seen[name] = seen
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    result["all"] = set(first_seen)
    result["new"] = {n: d.date().isoformat() for n, d in first_seen.items() if d >= cutoff}
    return result


def pagespeed(url: str, api_key: str | None = None) -> dict:
    """Mobile Lighthouse performance score (0 to 100) from PageSpeed Insights."""
    params = {"url": url, "strategy": "mobile", "category": "performance"}
    if api_key:
        params["key"] = api_key
    try:
        r = _session.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", params=params, timeout=120)
        r.raise_for_status()
        score = r.json()["lighthouseResult"]["categories"]["performance"]["score"]
        return {"score": round(score * 100) if score is not None else None, "error": None}
    except Exception as exc:
        return {"score": None, "error": f"PageSpeed failed: {exc}"[:300]}
