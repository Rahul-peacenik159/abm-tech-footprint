"""Load, merge and compile stack packs (YAML) into one flat dict."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

DEFAULT_PLAYS = {
    "competitor_found": "displacement_sequence",
    "complement_found": "integration_pitch",
    "gap_found": "gap_audit",
    "tool_added": "timing_trigger",
    "tool_removed": "timing_trigger",
    "competitor_removed": "switch_window_outreach",
    "subdomain_new": "launch_congrats_touch",
    "slow_site": "speed_audit",
}

PATTERN_KEYS = ("html", "headers", "dns_txt", "spf", "mx", "dmarc")
POSTURE_KINDS = ("email", "web")


class PackError(ValueError):
    pass


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise PackError(f"Pack not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise PackError(f"{path} must be a YAML mapping")
    return data


def load_pack(path: str | Path, _seen: set | None = None) -> dict:
    """Load a pack and everything it `extends`, child values winning."""
    path = Path(path)
    if path.suffix not in (".yaml", ".yml"):
        path = path.with_suffix(".yaml")
    _seen = _seen or set()
    if path.resolve() in _seen:
        raise PackError(f"Circular extends at {path}")
    _seen.add(path.resolve())

    raw = _read_yaml(path)
    merged: dict = {
        "pack": raw.get("pack", path.stem),
        "description": raw.get("description", ""),
        "tools": {},
        "weights": {},
        "plays": dict(DEFAULT_PLAYS),
        "interesting_subdomains": [],
        "extra_paths": [],
        "seller": {"product": "", "competitors": [], "complements": [], "must_have_categories": []},
        "posture": [],
        "posture_weights": {},
        "posture_plays": {},
    }

    for parent in raw.get("extends", []) or []:
        base = load_pack(path.parent / f"{parent}.yaml", _seen)
        merged["tools"].update(base["tools"])
        merged["weights"].update(base["weights"])
        merged["plays"].update(base["plays"])
        merged["interesting_subdomains"] += base["interesting_subdomains"]
        merged["extra_paths"] += base["extra_paths"]
        merged["posture"] += base["posture"]
        merged["posture_weights"].update(base["posture_weights"])
        merged["posture_plays"].update(base["posture_plays"])

    for tool_id, tool in (raw.get("tools") or {}).items():
        merged["tools"][tool_id] = _normalise_tool(tool_id, tool, path)
    merged["weights"].update(raw.get("weights") or {})
    merged["plays"].update(raw.get("plays") or {})
    merged["interesting_subdomains"] = sorted(set(merged["interesting_subdomains"]) | set(raw.get("interesting_subdomains") or []))
    merged["extra_paths"] = list(dict.fromkeys(merged["extra_paths"] + list(raw.get("extra_paths") or [])))
    merged["posture"] = sorted(set(merged["posture"]) | set(raw.get("posture") or []))
    merged["posture_weights"].update(raw.get("posture_weights") or {})
    merged["posture_plays"].update(raw.get("posture_plays") or {})
    if raw.get("seller"):
        merged["seller"].update({k: (v if k == "product" else (v or [])) for k, v in raw["seller"].items()})

    _validate(merged, path)
    return merged


def _normalise_tool(tool_id: str, tool: dict, path: Path) -> dict:
    if not isinstance(tool, dict) or "patterns" not in tool:
        raise PackError(f"{path}: tool '{tool_id}' needs a 'patterns' block")
    patterns = tool["patterns"] or {}
    unknown = set(patterns) - set(PATTERN_KEYS)
    if unknown:
        raise PackError(f"{path}: tool '{tool_id}' has unknown pattern keys {sorted(unknown)}")
    norm = {}
    for key in PATTERN_KEYS:
        val = patterns.get(key)
        if not val:
            continue
        if key == "headers":
            norm[key] = {str(h).lower(): str(v).lower() for h, v in val.items()}
        else:
            norm[key] = [p if str(p).startswith("re:") else str(p).lower() for p in val]
    return {
        "id": tool_id,
        "name": tool.get("name", tool_id),
        "category": tool.get("category", "other"),
        "patterns": norm,
        "httparchive": tool.get("httparchive"),
    }


def _validate(pack: dict, path: Path) -> None:
    tool_ids = set(pack["tools"])
    seller = pack["seller"]
    for key in ("competitors", "complements"):
        missing = [t for t in seller.get(key, []) if t not in tool_ids]
        if missing:
            raise PackError(f"{path}: seller.{key} lists unknown tool ids {missing}")
    bad = [k for k in pack["posture"] if k not in POSTURE_KINDS]
    if bad:
        raise PackError(f"{path}: unknown posture checks {bad}; use {list(POSTURE_KINDS)}")
    categories = {t["category"] for t in pack["tools"].values()}
    missing_cats = [c for c in seller.get("must_have_categories", []) if c not in categories]
    if missing_cats:
        raise PackError(f"{path}: seller.must_have_categories has categories no tool uses {missing_cats}")


def compile_pack(path: str | Path, out_dir: str | Path) -> Path:
    """Write the merged pack as JSON (used by the n8n workflow)."""
    pack = load_pack(path)
    out = Path(out_dir) / f"{pack['pack']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")
    return out


def list_packs(directory: str | Path) -> list[Path]:
    return sorted(p for p in Path(directory).glob("*.yaml") if not p.stem.startswith("_"))
