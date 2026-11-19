"""Offline tests: no network calls. Run with `pytest -q`."""
import csv
import json
from pathlib import Path

import pytest

from footprint import cli, detect, packs, signals

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "stack-packs"
FIXTURE = (ROOT / "tests" / "fixtures" / "hotel_homepage.html").read_text()


@pytest.fixture(scope="module")
def hospitality():
    return packs.load_pack(PACKS / "hospitality.yaml")


@pytest.mark.parametrize("path", packs.list_packs(PACKS), ids=lambda p: p.stem)
def test_every_pack_loads_and_compiles(path, tmp_path):
    pack = packs.load_pack(path)
    assert pack["tools"], "pack has no tools"
    assert "google_tag_manager" in pack["tools"], "pack should extend _core"
    out = packs.compile_pack(path, tmp_path)
    assert json.loads(out.read_text())["pack"] == pack["pack"]


def test_normalise_domain():
    assert detect.normalise_domain("https://www.Example.com/path?q=1") == "example.com"
    assert detect.normalise_domain("shop.example.co.uk") == "shop.example.co.uk"
    assert detect.normalise_domain("") == ""


def test_detects_tools_in_html_and_headers(hospitality):
    hits = detect.detect_web(FIXTURE, {"Server": "cloudflare", "CF-RAY": "abc"}, hospitality["tools"], "grandhotel.example")
    found = {h["tool"] for h in hits}
    assert {"synxis", "asksuite", "google_tag_manager", "meta_pixel", "wordpress", "cloudflare"} <= found
    assert "cvent" not in found


def test_host_boundary_avoids_false_positives():
    pack = packs.load_pack(PACKS / "restaurants.yaml")
    html = '<script src="https://cdn.polo.com/app.js"></script>'
    assert "olo" not in {h["tool"] for h in detect.detect_web(html, {}, pack["tools"])}
    html = '<a href="https://order.olo.com/menu">Order</a>'
    assert "olo" in {h["tool"] for h in detect.detect_web(html, {}, pack["tools"])}


def test_own_domain_is_ignored():
    pack = packs.load_pack(PACKS / "hospitality.yaml")
    html = '<a href="https://www.cloudbeds.com/pricing">Pricing</a>'
    assert detect.detect_web(html, {}, pack["tools"], own_domain="cloudbeds.com") == []


def test_dns_detection(hospitality):
    txt = ['"v=spf1 include:_spf.google.com include:sendgrid.net ~all"',
           "atlassian-domain-verification=abc123", "docusign=1234-5678"]
    mx = ["aspmx.l.google.com.", "alt1.aspmx.l.google.com."]
    found = {h["tool"]: h["source"] for h in detect.detect_dns(txt, mx, hospitality["tools"])}
    assert found["google_workspace"] in ("spf", "dns_mx")
    assert found["sendgrid"] == "spf"
    assert found["atlassian"] == "dns_txt"
    assert found["docusign"] == "dns_txt"
    assert "microsoft_365" not in found


def test_signals_roles_gaps_and_changes(hospitality):
    hits = detect.detect_web(FIXTURE, {}, hospitality["tools"], "grandhotel.example")
    rows = signals.build_signals(
        "grandhotel.example", hospitality, hits, fetched=True, page_url="https://grandhotel.example/",
        previous_tools={"synxis", "hijiffy"}, new_subdomains={"events.grandhotel.example": "2026-11-01",
                                                             "random.grandhotel.example": "2026-11-02"},
        pagespeed_score=31)
    by_type = {}
    for r in rows:
        by_type.setdefault(r["signal_type"], []).append(r)

    asksuite = next(r for r in by_type["tech_detected"] if r["signal_value"] == "asksuite")
    assert asksuite["role"] == "competitor" and asksuite["weight"] == 30
    synxis = next(r for r in by_type["tech_detected"] if r["signal_value"] == "synxis")
    assert synxis["role"] == "complement"
    assert "gap" not in by_type  # chat and booking engine both present
    assert any(r["signal_value"] == "asksuite" for r in by_type["tech_added"])
    removed = by_type["tech_removed"][0]
    assert removed["signal_value"] == "hijiffy" and removed["play"] == "switch_window_outreach"
    assert [r["signal_value"] for r in by_type["subdomain_new"]] == ["events.grandhotel.example"]
    assert by_type["pagespeed_mobile"][0]["weight"] == hospitality["weights"]["slow_site"]

    summary = signals.summarise("grandhotel.example", rows, True, [])
    assert summary["score"] <= 100
    assert summary["top_play"] == "switch_window_outreach"
    assert "Asksuite" in summary["competitors"]


def test_gap_when_category_missing(hospitality):
    rows = signals.build_signals("plain.example", hospitality, [], fetched=True, page_url=None)
    assert {r["signal_value"] for r in rows if r["signal_type"] == "gap"} == {"chat", "booking_engine"}
    assert signals.build_signals("down.example", hospitality, [], fetched=False, page_url=None) == []


def test_external_hosts():
    hosts = detect.external_hosts(FIXTURE, "grandhotel.example")
    assert "be.synxis.com" in hosts
    assert "www.googletagmanager.com" in hosts
    assert not any(h.endswith("grandhotel.example") for h in hosts)


def test_scan_end_to_end_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.fetch, "fetch_site", lambda d, p=None: {
        "ok": True, "url": f"https://{d}/", "html": FIXTURE if d == "grandhotel.example" else "<html></html>",
        "headers": {}, "error": None})
    monkeypatch.setattr(cli.fetch, "get_dns", lambda d: {"txt": ["v=spf1 include:spf.protection.outlook.com -all"],
                                                         "mx": ["x.mail.protection.outlook.com"], "error": None})
    args = ["scan", "--pack", "hospitality", "--domains", "grandhotel.example", "plainhotel.example",
            "--out", str(tmp_path), "--delay", "0"]
    cli.main(args)
    with open(tmp_path / "accounts_summary.csv") as fh:
        summary = {r["account_domain"]: r for r in csv.DictReader(fh)}
    assert "Asksuite" in summary["grandhotel.example"]["competitors"]
    assert summary["plainhotel.example"]["gaps"] == "booking_engine; chat"
    assert "Microsoft 365" in summary["plainhotel.example"]["all_tools"]
    snaps = list((tmp_path / "snapshots" / "hospitality").glob("*.jsonl"))
    assert len(snaps) == 1


def test_httparchive_sql_generation(capsys):
    cli.main(["httparchive-sql", "--pack", "ecommerce", "--accounts-table", "p.abm.accounts",
              "--signals-table", "p.abm.signals"])
    sql = capsys.readouterr().out
    assert "{{" not in sql
    assert "'Yotpo' AS technology, 'yotpo' AS tool_id" in sql
    assert "'competitor' AS role" in sql
    assert "`httparchive.crawl.pages`" in sql and "is_root_page" in sql


# ---------------------------------------------------------------- posture checks
from footprint import posture  # noqa: E402


def _ids(findings, status=None):
    return {f["id"] for f in findings if status is None or f["status"] == status}


def test_email_posture_flags_weak_setups():
    weak = posture.email_posture(["v=spf1 include:_spf.google.com ?all"], ["smtp.google.com"],
                                 ["v=DMARC1; p=none"], [], [])
    assert {"spf_permissive_all", "dmarc_monitor_only", "dmarc_no_reporting",
            "mta_sts_missing", "bimi_missing"} <= _ids(weak, "issue")

    partial = posture.email_posture(["v=spf1 -all"], ["mx.example.com"],
                                    ["v=DMARC1; p=quarantine; pct=25; sp=none; rua=mailto:d@example.com"])
    assert {"dmarc_partial_enforcement", "dmarc_subdomains_unprotected"} <= _ids(partial, "issue")
    assert "spf_hardfail" in _ids(partial, "ok")

    missing = posture.email_posture(["google-site-verification=x"], [], [])
    assert {"spf_missing", "dmarc_missing"} <= _ids(missing, "issue")
    assert "no_mx" in _ids(missing, "info")

    many = " ".join(f"include:s{i}.example.com" for i in range(11))
    assert "spf_too_many_lookups" in _ids(posture.email_posture([f"v=spf1 {many} -all"], ["mx"], []), "issue")

    good = posture.email_posture(["v=spf1 include:_spf.google.com ~all"], ["smtp.google.com"],
                                 ["v=DMARC1; p=reject; rua=mailto:d@vali.email"], ["v=STSv1; id=1"], ["v=BIMI1; l=x"])
    assert _ids(good, "issue") == set()


def test_web_posture():
    strong = {"strict-transport-security": "max-age=63072000", "content-security-policy": "frame-ancestors 'self'",
              "x-content-type-options": "nosniff", "referrer-policy": "no-referrer"}
    assert _ids(posture.web_posture(strong, True, "https://x.example/"), "issue") == set()
    weak = posture.web_posture({"server": "nginx/1.18.0"}, False, "https://x.example/")
    assert {"hsts_missing", "csp_missing", "clickjacking_unprotected", "nosniff_missing",
            "referrer_policy_missing", "server_version_exposed", "security_txt_missing"} <= _ids(weak, "issue")
    assert "hsts_short" in _ids(posture.web_posture({"strict-transport-security": "max-age=600"}, None), "issue")


def test_scan_from_raw_with_posture(tmp_path):
    raw = [{"domain": "startup.example", "url": "https://startup.example/",
            "headers": {"server": "Vercel", "x-vercel-id": ""},
            "html": "trust.startup.example\nconsent.cookiebot.com/uc.js\nsoc 2", "security_txt": False}]
    dns = {"startup.example": {"txt": ["v=spf1 include:_spf.google.com ~all", "openai-domain-verification=x"],
                               "mx": ["smtp.google.com"],
                               "dmarc": ["v=DMARC1; p=none; rua=mailto:d@startup.example"],
                               "mta_sts": [], "bimi": []}}
    (tmp_path / "raw.json").write_text(json.dumps(raw))
    (tmp_path / "dns.json").write_text(json.dumps(dns))
    for pack in ("security-compliance", "email-deliverability"):
        out = tmp_path / pack
        cli.main(["scan", "--pack", pack, "--from-raw", str(tmp_path / "raw.json"),
                  "--dns-raw", str(tmp_path / "dns.json"), "--out", str(out)])
        row = next(csv.DictReader(open(out / "accounts_summary.csv")))
        if pack == "security-compliance":
            assert "Trust center" in row["all_tools"] and "Cookiebot" in row["all_tools"]
            assert "Mentions SOC 2" in row["all_tools"] and "Vercel" in row["all_tools"]
            assert "csp_missing" in row["posture_issues"] and "security_txt_missing" in row["posture_issues"]
            assert "trust_center" not in row["gaps"]
        else:
            assert "dmarc_monitor_only" in row["posture_issues"]
            assert "OpenAI" in row["all_tools"] and "Google Workspace" in row["all_tools"]
            assert row["gaps"] == "dmarc_reporting"


def test_dmarc_vendor_detection():
    pack = packs.load_pack(PACKS / "email-deliverability.yaml")
    hits = detect.detect_dns([], [], pack["tools"], ["v=DMARC1; p=reject; rua=mailto:abc@ag.dmarcian.com"])
    assert {h["tool"]: h["source"] for h in hits}.get("dmarcian") == "dmarc"


def test_summary_markdown(tmp_path, capsys):
    f = tmp_path / "accounts_summary.csv"
    with f.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=signals.SUMMARY_FIELDS)
        w.writeheader()
        w.writerow({"account_domain": "a.example", "fetched": "True", "score": 40, "top_play": "dmarc_enforcement",
                    "posture_issues": "dmarc_monitor_only", "all_tools": "Google Workspace", "errors": ""})
    cli.main(["summary", str(f), "--title", "T"])
    out = capsys.readouterr().out
    assert "### T" in out and "| a.example | 40 | dmarc enforcement |" in out


def test_rerun_same_day_compares_with_previous(monkeypatch, tmp_path):
    pages = {"grandhotel.example": FIXTURE}
    monkeypatch.setattr(cli.fetch, "fetch_site", lambda d, p=None: {
        "ok": True, "url": f"https://{d}/", "html": pages[d], "headers": {}, "error": None})
    monkeypatch.setattr(cli.fetch, "get_dns", lambda d: {"txt": [], "mx": [], "error": None})
    args = ["scan", "--pack", "hospitality", "--domains", "grandhotel.example", "--out", str(tmp_path), "--delay", "0"]
    cli.main(args)
    assert json.loads((tmp_path / "run_info.json").read_text())["previous_scan"] is None
    pages["grandhotel.example"] = FIXTURE.replace("static.asksuite.com", "example.org")  # competitor removed
    cli.main(args)
    info = json.loads((tmp_path / "run_info.json").read_text())
    assert info["previous_scan"] and info["changes"] == 1
    with open(tmp_path / "accounts_summary.csv") as fh:
        row = next(csv.DictReader(fh))
    assert row["changes"] == "-Asksuite" and row["top_play"] == "switch_window_outreach"


def test_render_sees_injected_scripts(tmp_path):
    """Needs Playwright + Chromium; skipped otherwise (CI installs only the base requirements)."""
    pytest.importorskip("playwright.sync_api")
    import http.server
    import os
    import socketserver
    import threading

    (tmp_path / "index.html").write_text(
        "<html><head><script>setTimeout(function(){var s=document.createElement('script');"
        "s.src='/x/consent.' + 'cookiebot.com.js';document.head.appendChild(s);},200);</script></head>"
        "<body>hello</body></html>")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "consent.cookiebot.com.js").write_text("//")
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path), **k)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        try:
            with cli.fetch.Renderer(wait_ms=1000) as r:
                site = r.fetch_site("site.test", [], candidates=[url])
        except Exception as exc:  # Chromium not installed
            pytest.skip(f"browser not available: {exc}")
        finally:
            srv.shutdown()
    pack = packs.load_pack(PACKS / "security-compliance.yaml")
    assert "cookiebot" in {h["tool"] for h in detect.detect_web(site["html"], {}, pack["tools"], "site.test")}
