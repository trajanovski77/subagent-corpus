#!/usr/bin/env python3
"""Executable oracles, version 2: let the tool itself report what it loaded and what it granted.

    python3 code/oracles_v2.py resolver     # O2': effective tool set of every distinct tools/disallowedTools value
    python3 code/oracles_v2.py census       # O1': which specifications each configuration root actually loads
    python3 code/oracles_v2.py semantics    # controlled probes: shadowing order, nesting, sub-project roots
    python3 code/oracles_v2.py settings     # O3: diagnostics the settings layer prints for each settings.json
    python3 code/oracles_v2.py history      # default tool pools of earlier releases (legacy-name evidence)

THE OBSERVATION POINT
---------------------
In print mode with ``--output-format stream-json --verbose``, Claude Code emits a ``system/init`` event before
it contacts the model. The event lists the session's resolved ``tools`` and the registered ``agents``. With
``--agent <name>`` the tool list is the one that agent's frontmatter resolves to. Run with an empty, isolated
``CLAUDE_CONFIG_DIR`` there is no credential, so the model is never called; the process exits by itself once the
first request fails to authenticate. The observation costs nothing and involves no inference.

WHAT IT REPLACES, AND WHY
-------------------------
Version 1 derived defect labels from a 60-name vocabulary obtained through the permission-rule validator
(O2), which does not check names containing an underscore and is not the resolver that reads frontmatter.
Its O1 probe staged every file flat in one directory, so nesting and root semantics were never exercised.
Here the frontmatter resolver is observed directly, on the corpus's own values.

KNOWN LIMIT
-----------
Some tools are gated by server-side feature flags that are fetched only when authenticated
(``data/v2/oracles/authenticated_probes_2026-09-15.json``). An unauthenticated resolver therefore under-reports
those names; ``analysis`` adds them back from the recorded authenticated pool. Interactive-only tools cannot be
observed in print mode at all and are classified as context-conditional from the build's tool schema.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parsing  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
V2 = DATA / "v2"
ORA = V2 / "oracles"
TOOLS_DIR = ROOT.parent / ".tools"
CC = Path(os.environ.get("CLAUDE_BIN", str(TOOLS_DIR / "cc-2.1.233" / "node_modules" / ".bin" / "claude")))
ISO = TOOLS_DIR / "iso-config-oracle"
WORK = Path(tempfile.gettempdir()) / "subagent-oracles"
WORKERS = int(os.environ.get("ORACLE_WORKERS", "8"))


# ---------------------------------------------------------------------------------- probe
def init_event(cwd: Path, agent: str | None = None, extra: list[str] | None = None,
               cc: Path = CC, timeout: int = 60) -> tuple[dict | None, str]:
    """Run one unauthenticated print-mode session and return (init event, stderr)."""
    ISO.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_OAUTH")) and k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    env.update(CLAUDE_CONFIG_DIR=str(ISO), CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", DISABLE_AUTOUPDATER="1")
    cmd = [str(cc), "-p", "probe", "--output-format", "stream-json", "--verbose", "--strict-mcp-config",
           "--setting-sources", "project", "--no-session-persistence", *(extra or [])]
    if agent is not None:
        cmd += ["--agent", agent]
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        out, err = p.stdout, p.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = "timeout"
    for line in out.splitlines():
        if line.startswith("{"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "system" and e.get("subtype") == "init":
                return e, err
    return None, err


def fresh_dir(tag: str) -> Path:
    import hashlib
    d = WORK / (re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)[:80] + "_" + hashlib.sha1(tag.encode()).hexdigest()[:10])
    if d.exists():
        shutil.rmtree(d)
    (d / ".claude" / "agents").mkdir(parents=True)
    return d


def spec_text(name: str, tools=None, disallowed=None, has_tools=True, has_disallowed=False, body="probe body") -> str:
    fm: dict = {"name": name, "description": "probe"}
    if has_tools:
        fm["tools"] = tools
    if has_disallowed:
        fm["disallowedTools"] = disallowed
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n" + body + "\n"


# ------------------------------------------------------------------------------ resolver
def corpus_specs() -> list[dict]:
    specs = []
    with gzip.open(V2 / "agents.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("available") and r.get("is_spec"):
                specs.append(r)
    return specs


def raw_key(rec: dict) -> str:
    """Identity of a grant as the YAML parser saw it: tools and disallowedTools values, with presence."""
    return json.dumps({"tools": rec.get("tools_raw"), "has_tools": "tools" in (rec.get("fm_keys") or []),
                       "disallowed": rec.get("disallowedTools_raw", rec.get("disallowedTools")),
                       "has_disallowed": "disallowedTools" in (rec.get("fm_keys") or [])}, sort_keys=True)


def resolve_one(key: str) -> dict:
    k = json.loads(key)
    d = fresh_dir("res_" + str(abs(hash(key))))
    (d / ".claude" / "agents" / "p.md").write_text(
        spec_text("p", k["tools"], k["disallowed"], k["has_tools"], k["has_disallowed"]))
    ev, err = init_event(d, agent="p")
    shutil.rmtree(d, ignore_errors=True)
    if ev is None:
        return {"key": key, "ok": False, "stderr": err[-300:]}
    return {"key": key, "ok": True, "resolved": ev.get("tools"), "agents": ev.get("agents"),
            "version": ev.get("claude_code_version")}


def resolver() -> None:
    ORA.mkdir(parents=True, exist_ok=True)
    out = ORA / "resolver_unauth.jsonl"
    done = {json.loads(l)["key"] for l in out.read_text().splitlines()} if out.exists() else set()
    specs = corpus_specs()
    keys = sorted({raw_key(s) for s in specs} - done)
    print(f"{len(specs):,} specifications, {len(keys) + len(done):,} distinct grants, {len(keys):,} to probe", flush=True)
    base, _ = init_event(fresh_dir("baseline"))
    (ORA / "baseline_unauth.json").write_text(json.dumps(base, indent=1))
    n = 0
    with open(out, "a") as fh, cf.ThreadPoolExecutor(WORKERS) as ex:
        for rec in ex.map(resolve_one, keys):
            fh.write(json.dumps(rec) + "\n")
            n += 1
            if n % 500 == 0:
                fh.flush()
                print(f"  {n:,}/{len(keys):,}", flush=True)
    print("resolver done", flush=True)


# -------------------------------------------------------------------------------- census
def census_one(item: tuple[str, str, list[dict]]) -> dict:
    repo, root, files = item
    d = fresh_dir(f"cen_{repo}_{root}")
    for f in files:
        target = d / ".claude" / "agents" / f["rel_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"])
    ev, err = init_event(d)
    shutil.rmtree(d, ignore_errors=True)
    rec = {"repo": repo, "config_root": root, "n_files": len(files)}
    if ev is None:
        rec.update(ok=False, stderr=err[-300:])
    else:
        rec.update(ok=True, agents=ev.get("agents"))
    return rec


def census() -> None:
    ORA.mkdir(parents=True, exist_ok=True)
    out = ORA / "census.jsonl"
    done = set()
    if out.exists():
        for l in out.read_text().splitlines():
            r = json.loads(l)
            done.add((r["repo"], r["config_root"]))
    groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    with open(DATA / "work" / "blobs.jsonl") as fh:
        for line in fh:
            r = json.loads(line)
            if r["kind"] != "agent" or r["status"] != "ok":
                continue
            loc = parsing.locate(r["path"])
            groups[(r["repo"], loc["config_root"])].append({"rel_path": loc["rel_path"], "content": r["content"]})
    items = [(repo, root, files) for (repo, root), files in groups.items() if (repo, root) not in done]
    print(f"{len(groups):,} configuration roots, {len(items):,} to probe", flush=True)
    base, _ = init_event(fresh_dir("baseline"))
    builtin = sorted(base.get("agents") or []) if base else []
    (ORA / "builtin_agents.json").write_text(json.dumps(builtin))
    n = 0
    with open(out, "a") as fh, cf.ThreadPoolExecutor(WORKERS) as ex:
        for rec in ex.map(census_one, items):
            fh.write(json.dumps(rec) + "\n")
            n += 1
            if n % 250 == 0:
                fh.flush()
                print(f"  {n:,}/{len(items):,}", flush=True)
    print("census done", flush=True)


# ----------------------------------------------------------------------------- semantics
def semantics() -> None:
    """Controlled probes whose answers the corpus analysis depends on."""
    ORA.mkdir(parents=True, exist_ok=True)
    results = {}

    def agents_of(d):
        ev, _ = init_event(d)
        return sorted(set(ev.get("agents") or []) - set(builtin)) if ev else None

    def tools_of(d, name):
        ev, _ = init_event(d, agent=name)
        return ev.get("tools") if ev else None

    base, _ = init_event(fresh_dir("sem_base"))
    builtin = base.get("agents") or []
    results["builtin_agents"] = builtin

    # 1. shadowing: same name, different tools, in several arrangements
    arrangements = {
        "same_dir_a_vs_b": [("a.md", "Read"), ("b.md", "Write")],
        "same_dir_b_vs_a_reversed_tools": [("a.md", "Write"), ("b.md", "Read")],
        "top_vs_nested": [("z.md", "Read"), ("sub/a.md", "Write")],
        "nested_vs_top": [("a.md", "Write"), ("sub/z.md", "Read")],
        "two_nested_dirs": [("x/a.md", "Read"), ("y/a.md", "Write")],
    }
    for label, files in arrangements.items():
        d = fresh_dir("sem_shadow_" + label)
        for rel, tools in files:
            p = d / ".claude" / "agents" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(spec_text("dup", tools))
        results["shadow_" + label] = {"files": files, "agents": agents_of(d), "winner_tools": tools_of(d, "dup")}

    # 2. nesting depth
    d = fresh_dir("sem_nesting")
    for rel in ("top.md", "one/nested1.md", "one/two/nested2.md", "one/two/three/nested3.md"):
        p = d / ".claude" / "agents" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(spec_text(Path(rel).stem, "Read"))
    results["nesting_loaded"] = agents_of(d)

    # 3. a sub-project's .claude/agents is not loaded from the repository root, and vice versa
    d = fresh_dir("sem_roots")
    (d / ".claude" / "agents" / "rootagent.md").write_text(spec_text("rootagent", "Read"))
    (d / "packages" / "web" / ".claude" / "agents").mkdir(parents=True)
    (d / "packages" / "web" / ".claude" / "agents" / "subagent.md").write_text(spec_text("subagent", "Read"))
    results["roots_from_repo_root"] = agents_of(d)
    ev, _ = init_event(d / "packages" / "web")
    results["roots_from_subproject"] = sorted(set(ev.get("agents") or []) - set(builtin)) if ev else None

    # 4. name field vs file name; non-string name; missing description; non-.md file
    d = fresh_dir("sem_admission")
    ag = d / ".claude" / "agents"
    (ag / "file-name.md").write_text(spec_text("declared-name", "Read"))
    (ag / "listname.md").write_text("---\nname: [a, b]\ndescription: probe\n---\nbody\n")
    (ag / "nodesc.md").write_text("---\nname: nodesc\n---\nbody\n")
    (ag / "notmd.txt").write_text(spec_text("notmd", "Read"))
    (ag / "upper.MD").write_text(spec_text("upperext", "Read"))
    (ag / "spaced.md").write_text(spec_text("Spaced Name", "Read"))
    results["admission_loaded"] = agents_of(d)

    # 5. disallowedTools semantics
    d = fresh_dir("sem_disallowed")
    ag = d / ".claude" / "agents"
    (ag / "omit_dis.md").write_text(spec_text("omit_dis", None, "Write, Edit, Bash", has_tools=False, has_disallowed=True))
    (ag / "list_dis.md").write_text(spec_text("list_dis", "Read, Write, Bash", "Write", has_tools=True, has_disallowed=True))
    results["disallowed_with_omitted_tools"] = tools_of(d, "omit_dis")
    results["disallowed_with_list"] = tools_of(d, "list_dis")

    # 6. string forms of the tools field
    for label, value in {"space_separated": "Read Grep Bash", "lowercase": "read, bash", "yaml_list": ["Read", "Bash"],
                         "scoped_bash": "Read, Bash(git diff:*)", "wildcard_string": "*", "all_word": "all",
                         "empty_string": "", "json_like": "[Read, Bash]", "mcp_name": "Read, mcp__github__create_issue",
                         "powershell": "Read, PowerShell", "grep_glob_scoped_bash": "Read, Grep, Glob, Bash(npm test)"}.items():
        d = fresh_dir("sem_form_" + label)
        (d / ".claude" / "agents" / "f.md").write_text(spec_text("f", value))
        results["form_" + label] = {"value": value, "resolved": tools_of(d, "f")}

    ev, _ = init_event(fresh_dir("sem_version"))
    results["version"] = ev.get("claude_code_version") if ev else None
    (ORA / "semantics.json").write_text(json.dumps(results, indent=1) + "\n")
    print(json.dumps(results, indent=1))


# ------------------------------------------------------------------------------ settings
def settings_one(item: tuple[str, str, str]) -> dict:
    """O3. The settings layer validates deny and ask rules at start-up and prints one warning per rule that
    matches no known tool. The warning appears in plain-text print mode, not in stream-json mode."""
    repo, path, content = item
    d = fresh_dir(f"set_{repo}_{path}")
    (d / ".claude" / "settings.json").write_text(content)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_OAUTH"))}
    env.update(CLAUDE_CONFIG_DIR=str(ISO), CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", DISABLE_AUTOUPDATER="1")
    try:
        p = subprocess.run([str(CC), "-p", "probe", "--setting-sources", "project", "--strict-mcp-config",
                            "--no-session-persistence"], cwd=d, env=env, capture_output=True, text=True,
                           timeout=60, stdin=subprocess.DEVNULL)
        text = p.stdout + "\n" + p.stderr
    except subprocess.TimeoutExpired:
        text = "timeout"
    shutil.rmtree(d, ignore_errors=True)
    warnings = re.findall(r'Permission (deny|ask|allow) rule "(.*?)" matches no known tool', text)
    other = [l for l in text.splitlines() if l.strip() and "matches no known tool" not in l
             and "Not logged in" not in l and "Invalid API key" not in l and "authenticat" not in l.lower()]
    return {"repo": repo, "path": path, "void_rules": [{"kind": k, "rule": r} for k, r in warnings],
            "other_output": other[:10]}


def settings() -> None:
    ORA.mkdir(parents=True, exist_ok=True)
    out = ORA / "settings_diagnostics.jsonl"
    done = set()
    if out.exists():
        done = {(json.loads(l)["repo"], json.loads(l)["path"]) for l in out.read_text().splitlines()}
    items = []
    with open(DATA / "work" / "blobs.jsonl") as fh:
        for line in fh:
            r = json.loads(line)
            if r["kind"] == "settings" and r["status"] == "ok" and (r["repo"], r["path"]) not in done:
                items.append((r["repo"], r["path"], r["content"]))
    print(f"{len(items):,} settings files to probe", flush=True)
    with open(out, "a") as fh, cf.ThreadPoolExecutor(WORKERS) as ex:
        for i, rec in enumerate(ex.map(settings_one, items), 1):
            fh.write(json.dumps(rec) + "\n")
            if i % 250 == 0:
                fh.flush()
                print(f"  {i:,}/{len(items):,}", flush=True)


# ------------------------------------------------------------------------------- history
def history(versions: list[str]) -> None:
    """Default tool pool of earlier releases, installed one at a time and removed afterwards."""
    ORA.mkdir(parents=True, exist_ok=True)
    out = ORA / "tool_pool_history.jsonl"
    done = {json.loads(l)["requested"] for l in out.read_text().splitlines()} if out.exists() else set()
    for v in versions:
        if v in done:
            continue
        prefix = TOOLS_DIR / f"hist-{v}"
        rec = {"requested": v}
        try:
            subprocess.run(["npm", "install", "--prefix", str(prefix), "--no-audit", "--no-fund",
                            f"@anthropic-ai/claude-code@{v}"], capture_output=True, text=True, timeout=600, check=True)
            binpath = prefix / "node_modules" / ".bin" / "claude"
            d = fresh_dir(f"hist_{v}")
            ev, err = init_event(d, cc=binpath)
            if ev is None:   # early releases lack some flags; retry with the minimal set
                env = {k: val for k, val in os.environ.items() if not k.startswith("ANTHROPIC_")}
                env.update(CLAUDE_CONFIG_DIR=str(ISO))
                p = subprocess.run([str(binpath), "-p", "probe", "--output-format", "stream-json", "--verbose"],
                                   cwd=d, env=env, capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL)
                ev = next((json.loads(l) for l in p.stdout.splitlines()
                           if l.startswith("{") and '"subtype":"init"' in l.replace(" ", "")), None)
                err = p.stderr
            rec.update(ok=ev is not None, version=(ev or {}).get("claude_code_version"),
                       tools=(ev or {}).get("tools"), stderr=err[-300:] if ev is None else "")
        except Exception as exc:  # record, never guess
            rec.update(ok=False, error=str(exc)[:300])
        finally:
            shutil.rmtree(prefix, ignore_errors=True)
        with open(out, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(v, rec.get("ok"), (rec.get("tools") or [])[:40], flush=True)


# --------------------------------------------------------------------------------- names
def names() -> None:
    """Resolve every distinct tool name on its own, so unresolved names can be told apart from names that
    resolve individually but are dropped in combination (Grep and Glob when Bash is granted)."""
    ORA.mkdir(parents=True, exist_ok=True)
    out = ORA / "names_unauth.jsonl"
    done = {json.loads(l)["name"] for l in out.read_text().splitlines()} if out.exists() else set()
    counts = collections.Counter()
    for s in corpus_specs():
        for t in parsing.normalise_tools(s.get("tools_raw")) or []:
            counts[parsing.base_tool(t)] += 1
    # MCP tool names resolve only when their server is configured; they are classified by construction.
    todo = [n for n, _ in counts.most_common() if n not in done and not n.startswith("mcp__")]
    print(f"{len(counts):,} distinct base names, {len(todo):,} non-MCP names to probe", flush=True)

    def one(name: str) -> dict:
        d = fresh_dir("name_" + name)
        (d / ".claude" / "agents" / "p.md").write_text(spec_text("p", [name]))
        ev, err = init_event(d, agent="p")
        shutil.rmtree(d, ignore_errors=True)
        return {"name": name, "occurrences": counts[name], "ok": ev is not None,
                "resolved": ev.get("tools") if ev else None}

    with open(out, "a") as fh, cf.ThreadPoolExecutor(WORKERS) as ex:
        for i, rec in enumerate(ex.map(one, todo), 1):
            fh.write(json.dumps(rec) + "\n")
            if i % 500 == 0:
                fh.flush()
                print(f"  {i:,}/{len(todo):,}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["resolver", "census", "semantics", "settings", "history", "names"])
    ap.add_argument("--versions", default="")
    a = ap.parse_args()
    if a.mode == "history":
        history([v for v in a.versions.split(",") if v])
    else:
        {"resolver": resolver, "census": census, "semantics": semantics, "settings": settings, "names": names}[a.mode]()
