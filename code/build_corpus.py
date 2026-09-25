#!/usr/bin/env python3
"""Build corpus v2 from the snapshot-exact reconstruction.

    python3 code/build_corpus.py

Inputs : data/trees.jsonl.gz (inventory), data/work/blobs.jsonl (``reconstruct.py``), data/agents.jsonl.gz (v1)
Outputs: data/v2/agents.jsonl.gz      one record per inventoried agent file, available or not
         data/v2/bodies.jsonl.gz      full description and body text of every specification
         data/v2/governance.jsonl.gz  one record per repository: parsed settings, .mcp.json and CI workflows
         data/v2/build_report.json    coverage and v1-vs-v2 reconciliation numbers

Every inventoried file gets a record, so coverage is part of the data: ``available`` is false when the
repository or object no longer exists, and ``status`` says which.
"""
from __future__ import annotations

import collections
import gzip
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parsing  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BLOBS = DATA / "work" / "blobs.jsonl"
OUT = DATA / "v2"
IS_AGENT = re.compile(r"(^|/)\.claude/agents/.*\.md$")
CLAUDE_ACTION = re.compile(r"anthropics/claude-code(-base)?-action", re.I)


def load_yaml(text: str):
    try:
        return yaml.safe_load(text)
    except Exception:
        return None


def summarise_settings(text: str) -> dict:
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return {"parse_ok": False}
    if not isinstance(d, dict):
        return {"parse_ok": False}
    perm = d.get("permissions") if isinstance(d.get("permissions"), dict) else {}
    allow = [str(x) for x in perm.get("allow") or [] if isinstance(perm.get("allow"), list)]
    deny = [str(x) for x in perm.get("deny") or [] if isinstance(perm.get("deny"), list)]
    ask = [str(x) for x in perm.get("ask") or [] if isinstance(perm.get("ask"), list)]
    return {
        "parse_ok": True, "keys": sorted(d.keys()),
        "allow": len(allow), "deny": len(deny), "ask": len(ask),
        "default_mode": perm.get("defaultMode"),
        "allow_unscoped_bash": any(a.strip() in ("Bash", "Bash(*)", "Bash(**)") for a in allow),
        "deny_mentions_write": any(re.match(r"^(Write|Edit|NotebookEdit)\b", x) for x in deny),
        "deny_mentions_bash": any(x.startswith("Bash") for x in deny),
        "sandbox_enabled": bool((d.get("sandbox") or {}).get("enabled")) if isinstance(d.get("sandbox"), dict) else False,
        "hooks": bool(d.get("hooks")),
        "disable_bypass": perm.get("disableBypassPermissionsMode") == "disable",
    }


def summarise_workflow(text: str) -> dict:
    d = load_yaml(text)
    if not isinstance(d, dict):
        return {"parse_ok": False}
    on = d.get("on", d.get(True))
    triggers = set()
    if isinstance(on, str):
        triggers = {on}
    elif isinstance(on, list):
        triggers = {str(x) for x in on}
    elif isinstance(on, dict):
        triggers = {str(k) for k in on}

    def classify(p) -> str:
        if p is None:
            return "unset"
        if isinstance(p, str):
            return {"write-all": "write-all", "read-all": "read-all"}.get(p, "other")
        if isinstance(p, dict):
            if not p:
                return "none"
            return "scoped-write" if any(str(v) == "write" for v in p.values()) else "scoped-read"
        return "other"

    jobs = d.get("jobs") if isinstance(d.get("jobs"), dict) else {}
    job_perms = [classify((j or {}).get("permissions")) for j in jobs.values() if isinstance(j, dict)]
    return {
        "parse_ok": True, "top_permissions": classify(d.get("permissions")),
        "job_permissions": job_perms,
        "contents_write": bool(re.search(r"contents:\s*write", text)),
        "write_all": "write-all" in text,
        "pull_request_target": "pull_request_target" in triggers,
        "uses_claude_action": bool(CLAUDE_ACTION.search(text)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = []
    with gzip.open(DATA / "trees.jsonl.gz", "rt") as fh:
        for line in fh:
            t = json.loads(line)
            for f in t["cfg"]:
                if IS_AGENT.search("/" + f["p"]):
                    inventory.append((t["repo"], f["p"], f["sha"], f.get("s")))
    blobs: dict[tuple[str, str], dict] = {}
    governance: dict[str, dict] = collections.defaultdict(lambda: {"settings": [], "settings_local": [], "mcp": [], "workflows": []})
    with open(BLOBS) as fh:
        for line in fh:
            r = json.loads(line)
            key = (r["repo"], r["path"])
            if r["kind"] == "agent":
                blobs[key] = r
                continue
            if r["status"] != "ok":
                continue
            g = governance[r["repo"]]
            loc = r["path"]
            if r["kind"] in ("settings", "settings_local"):
                g[r["kind"]].append({"path": loc, **summarise_settings(r["content"])})
            elif r["kind"] == "mcp":
                try:
                    servers = (json.loads(r["content"]) or {}).get("mcpServers") or {}
                    g["mcp"].append({"path": loc, "servers": len(servers) if isinstance(servers, dict) else None})
                except (json.JSONDecodeError, AttributeError):
                    g["mcp"].append({"path": loc, "servers": None})
            elif r["kind"] == "workflow":
                g["workflows"].append({"path": loc, **summarise_workflow(r["content"])})

    v1 = {}
    with gzip.open(DATA / "agents.jsonl.gz", "rt") as fh:
        for line in fh:
            a = json.loads(line)
            v1[(a["repo"], a["path"])] = a.get("hash")

    status = collections.Counter()
    n_spec = 0
    spec_repos = set()
    same_as_v1 = changed_vs_v1 = new_in_v2 = 0
    with gzip.open(OUT / "agents.jsonl.gz", "wt") as fa, gzip.open(OUT / "bodies.jsonl.gz", "wt") as fb:
        for repo, path, sha, size in inventory:
            b = blobs.get((repo, path))
            rec = {"repo": repo, "path": path, "sha": sha, "inventory_bytes": size, **parsing.locate(path)}
            if b is None or b["status"] != "ok":
                rec.update(available=False, status=(b or {}).get("status", "not-attempted"))
                status[rec["status"]] += 1
                fa.write(json.dumps(rec) + "\n")
                continue
            raw = b["content"]
            parsed = parsing.parse_specification(repo, path, raw)
            parsed["tools"] = parsing.normalise_tools(parsed.get("tools_raw"))
            fm_text, body = parsing.split_frontmatter(raw)
            rec.update(available=True, status="ok", sha_verified=b.get("sha_ok"), **parsed)
            rec["is_spec"] = parsing.is_specification(parsed)
            rec["in_v1"] = (repo, path) in v1
            if rec["in_v1"]:
                if v1[(repo, path)] == b["hash"]:
                    same_as_v1 += 1
                else:
                    changed_vs_v1 += 1
            else:
                new_in_v2 += 1
            status["ok"] += 1
            fa.write(json.dumps(rec) + "\n")
            if rec["is_spec"]:
                n_spec += 1
                spec_repos.add(repo)
                fb.write(json.dumps({"repo": repo, "path": path, "sha": sha, "hash": b["hash"],
                                     "name": parsed.get("name"), "description": parsed.get("description"),
                                     "body": body}) + "\n")
    with gzip.open(OUT / "governance.jsonl.gz", "wt") as fg:
        for repo, g in sorted(governance.items()):
            fg.write(json.dumps({"repo": repo, **g}) + "\n")

    report = {
        "inventory_agent_files": len(inventory), "status": dict(status),
        "specifications": n_spec, "specification_repositories": len(spec_repos),
        "v1_files": len(v1), "v1_files_identical_in_v2": same_as_v1, "v1_files_differing_in_v2": changed_vs_v1,
        "files_new_in_v2": new_in_v2, "repositories_with_governance_files": len(governance),
    }
    (OUT / "build_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
