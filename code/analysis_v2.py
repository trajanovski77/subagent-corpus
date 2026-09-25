#!/usr/bin/env python3
"""Every number in the revised paper, organised by research question.

    python3 code/analysis_v2.py table          # join all sources into data/v2/spec_table.jsonl.gz
    python3 code/analysis_v2.py all            # print every RQ section (reads the table)
    python3 code/analysis_v2.py rq2            # one section

Populations
  ALL  every specification in corpus v2 (69,316 in 4,128 repositories)
  ENG  specifications in repositories that pass the engineered-project filter (primary population)
Every prevalence is a mean of per-repository proportions with a percentile bootstrap over repositories
(``stats.py``); pooled rates are printed alongside for contrast. Contrasts between role groups are paired within
repository. No regression model is fitted: repository-level associations are differences of repository means with
bootstrap intervals and Fisher's exact test.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parsing  # noqa: E402
import stats  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
V2 = DATA / "v2"
ORA = V2 / "oracles"
TABLE = V2 / "spec_table.jsonl.gz"

FILE_WRITE = {"Write", "Edit", "NotebookEdit"}
SHELL = {"Bash", "PowerShell", "Monitor"}   # Monitor runs a shell command (credential-gated tool)
AUTH_ONLY = None    # filled from the recorded authenticated probes
NAME_CLASS: dict = {}   # tool name -> resolution class


def heading(t: str) -> None:
    print("\n" + "=" * 96 + f"\n{t}\n" + "=" * 96)


def jl(path: Path):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


# ----------------------------------------------------------------------------------- table
def build_table() -> None:
    global AUTH_ONLY
    auth = json.loads((ORA / "authenticated_probes_2026-09-15.json").read_text())
    AUTH_ONLY = set(auth["default_pool_authenticated"]) - set(auth["default_pool_unauthenticated"])

    from oracles_v2 import raw_key  # same key the resolver used
    resolved = {r["key"]: r["resolved"] for r in jl(ORA / "resolver_unauth.jsonl") if r["ok"]}
    global NAME_CLASS
    NAME_CLASS = json.loads((ORA / "name_classes.json").read_text())["classes"]
    text_keys = {(r["repo"], r["path"]): r["text_key"] for r in jl(V2 / "nlp" / "spec_text_keys.jsonl.gz")} \
        if (V2 / "nlp" / "spec_text_keys.jsonl.gz").exists() else {}
    # Haiku is the primary rater and wins wherever it labelled an item; Sonnet only fills the 400 pilot
    # items Haiku never saw. Its reliability labels must not replace the primary ones, or the analysed
    # labels would come from two raters. Reading only one file silently leaves role columns null.
    roles = {}
    for rater in ("sonnet", "haiku"):
        p = V2 / "labels" / f"roles_{rater}.jsonl.gz"
        if p.exists():
            roles.update({r["id"]: r for r in jl(p)})
    print(f"  role labels: {len(roles):,}")
    eng = {}
    if (V2 / "engineered.jsonl.gz").exists():
        eng = {r["repo"]: r for r in jl(V2 / "engineered.jsonl.gz")}
    from llm_labels import item_id, text as ltext

    n = 0
    with gzip.open(TABLE, "wt") as out:
        for r in jl(V2 / "agents.jsonl.gz"):
            if not (r.get("available") and r.get("is_spec")):
                continue
            raw_tools = parsing.normalise_tools(r.get("tools_raw"))
            fm_keys = r.get("fm_keys") or []
            has_tools = "tools" in fm_keys
            eff = resolved.get(raw_key(r))
            requested = [parsing.base_tool(t) for t in (raw_tools or [])]
            flag_gated = sorted({t for t in requested if t in AUTH_ONLY})
            eff_auth = sorted(set(eff or []) | set(flag_gated))
            if not has_tools or r.get("tools_raw") is None:
                grant = "implicit"
            elif raw_tools == ["*"]:
                grant = "wildcard"
            else:
                grant = "explicit"
            scoped_bash = [t for t in (raw_tools or []) if t.startswith("Bash(")]
            unscoped_bash = [t for t in (raw_tools or []) if t == "Bash"]
            # per-name classification (data/v2/oracles/name_classes.json), built from the resolver,
            # the build's tool schema and the tool-pool history of 48 releases
            cls = collections.Counter(NAME_CLASS.get(t, "never_valid") for t in requested)
            unresolved = [t for t in requested if NAME_CLASS.get(t, "never_valid") in ("removed_legacy", "never_valid")]
            iid = item_id(ltext(r.get("name")), ltext(r.get("description")))
            lab = roles.get(iid, {})
            row = {
                "repo": r["repo"], "path": r["path"], "config_root": r.get("config_root"), "nested": r.get("nested"),
                "root_is_repo_root": r.get("root_is_repo_root"), "hash": r.get("hash"), "bytes": r.get("bytes"),
                "name": ltext(r.get("name"))[:200], "item_id": iid, "text_key": text_keys.get((r["repo"], r["path"])),
                "grant": grant, "requested": requested, "n_requested": len(requested),
                "effective": eff_auth, "resolver_ok": eff is not None,
                "can_write_files": bool(set(eff_auth) & FILE_WRITE), "can_shell": bool(set(eff_auth) & SHELL),
                "shell_scoped_only": bool(scoped_bash) and not unscoped_bash,
                "resolves_nothing": grant == "explicit" and eff is not None and len(eff_auth) == 0,
                "unresolved_names": unresolved,
                "n_removed_legacy": cls["removed_legacy"], "n_never_valid": cls["never_valid"],
                "n_context_conditional": cls["interactive_only"] + cls["flag_gated"] + cls["platform_conditional"],
                "n_mcp_names": cls["mcp_conditional"], "n_alias": cls["alias"], "n_whitespace_split": cls["whitespace_split"],
                "grep_glob_dropped": grant == "explicit" and bool({"Grep", "Glob"} & set(requested))
                                     and "Bash" in requested and not ({"Grep", "Glob"} & set(eff_auth)),
                "disallowed": r.get("disallowedTools"), "model": r.get("model"),
                "permissionMode": r.get("permissionMode"), "color": r.get("color"), "memory": r.get("memory"),
                "maxTurns": r.get("maxTurns"), "isolation": r.get("isolation"), "background": r.get("background"),
                "effort": r.get("effort"), "has_hooks": r.get("has_hooks"), "fm_keys": fm_keys,
                "role": lab.get("role"), "mode": lab.get("mode"), "readonly_claim": lab.get("readonly_claim"),
                "lang": lab.get("lang"), "boilerplate": lab.get("boilerplate"),
                "E1": (eng.get(r["repo"]) or {}).get("E1"), "E2": (eng.get(r["repo"]) or {}).get("E2"),
                "E3": (eng.get(r["repo"]) or {}).get("E3"),
                "readme_category": (eng.get(r["repo"]) or {}).get("readme_category"),
            }
            out.write(json.dumps(row) + "\n")
            n += 1
    print(f"wrote {n:,} rows to {TABLE.relative_to(ROOT)}")


def load(population: str = "ALL") -> list[dict]:
    rows = list(jl(TABLE))
    if population in ("E1", "E2", "E3"):
        rows = [r for r in rows if r.get(population)]
    return rows


def est_line(label: str, e) -> None:
    if e is None:
        print(f"  {label:<58s} n/a")
    else:
        print(f"  {label:<58s} {100*e.mean:5.1f}% [{100*e.lo:4.1f},{100*e.hi:4.1f}]  repos={e.n_repos:>5,}  pooled {100*e.pooled:5.1f}%")


# ----------------------------------------------------------------------------------- RQ2
def rq2(pop: str) -> None:
    rows = load(pop)
    heading(f"RQ2  CAPABILITY GRANTS  [{pop}: {len(rows):,} specs, {len({r['repo'] for r in rows}):,} repos]")
    for g in ("implicit", "explicit", "wildcard"):
        est_line(f"grant type = {g}", stats.estimate(rows, lambda s, g=g: s["grant"] == g))
    print("\n  capability on the EFFECTIVE grant (resolver), by grant type")
    for g in ("implicit", "explicit"):
        pop_ = lambda s, g=g: s["grant"] == g
        est_line(f"  [{g}] can write files", stats.estimate(rows, lambda s: s["can_write_files"], pop_))
        est_line(f"  [{g}] can run a shell", stats.estimate(rows, lambda s: s["can_shell"], pop_))
        est_line(f"  [{g}] can write files or run a shell",
                 stats.estimate(rows, lambda s: s["can_write_files"] or s["can_shell"], pop_))
    ex = [r for r in rows if r["grant"] == "explicit"]
    if ex:
        print(f"\n  explicit lists: median requested {st.median([r['n_requested'] for r in ex]):.0f}, "
              f"median effective {st.median([len(r['effective']) for r in ex]):.0f}")
    has_roles = any(r.get("mode") for r in rows)
    if not has_roles:
        print("\n  (role labels not merged yet)")
        return
    inspect = lambda s: s.get("mode") == "inspect"
    change = lambda s: s.get("mode") == "change"
    print("\n  paired contrasts: inspect-mode vs change-mode specifications (same repository)")
    for label, outcome in (("can write files", lambda s: s["can_write_files"]),
                           ("can write files or run a shell", lambda s: s["can_write_files"] or s["can_shell"])):
        for gl, gp in (("all grants", lambda s: True), ("explicit only", lambda s: s["grant"] == "explicit")):
            sub = [r for r in rows if gp(r)]
            c = stats.paired_contrast(sub, inspect, change, outcome)
            if c:
                print(f"    {label:<32s} {gl:<14s} {100*c['difference']:+5.1f} pts [{100*c['lo']:+5.1f},{100*c['hi']:+5.1f}]  n={c['n_repos']}")
    print("\n  share of inspect-mode specifications that omit tools: (implicit inheritance)")
    est_line("inspect-mode: implicit", stats.estimate(rows, lambda s: s["grant"] == "implicit", inspect))
    est_line("change-mode: implicit", stats.estimate(rows, lambda s: s["grant"] == "implicit", change))


# ----------------------------------------------------------------------------------- RQ3
def rq3(pop: str) -> None:
    rows = load(pop)
    heading(f"RQ3  COHERENCE OF RESTRICTIONS  [{pop}]")
    ex = [r for r in rows if r["grant"] == "explicit" and r["resolver_ok"]]
    withheld = lambda s: s["grant"] == "explicit" and not s["can_write_files"]
    est_line("explicit lists withholding file-write tools", stats.estimate(rows, withheld, lambda s: s["grant"] == "explicit"))
    est_line("...of those, an unscoped shell is granted (incoherent)",
             stats.estimate(rows, lambda s: s["can_shell"] and not s["shell_scoped_only"], withheld))
    est_line("...of those, a shell is granted only as scoped Bash(...)",
             stats.estimate(rows, lambda s: s["shell_scoped_only"], withheld))
    est_line("explicit lists naming Grep/Glob with Bash: search tools dropped by the runtime",
             stats.estimate(rows, lambda s: s["grep_glob_dropped"],
                            lambda s: s["grant"] == "explicit" and bool({"Grep", "Glob"} & set(s["requested"]))))
    if any(r.get("mode") for r in rows):
        insp = lambda s: s.get("mode") == "inspect" and s["grant"] == "explicit"
        est_line("inspect-mode explicit lists withholding file-write", stats.estimate(rows, lambda s: not s["can_write_files"], insp))
        est_line("...and granting an unscoped shell",
                 stats.estimate(rows, lambda s: s["can_shell"] and not s["shell_scoped_only"], lambda s: insp(s) and not s["can_write_files"]))
        est_line("inspect-mode specs genuinely unable to write (effective grant)",
                 stats.estimate(rows, lambda s: not s["can_write_files"] and not s["can_shell"], lambda s: s.get("mode") == "inspect"))


# ----------------------------------------------------------------------------------- RQ1
def rq1(pop: str) -> None:
    rows = load(pop)
    repos = collections.defaultdict(list)
    for r in rows:
        repos[r["repo"]].append(r)
    heading(f"RQ1  DELEGATION STRUCTURE  [{pop}: {len(rows):,} specs, {len(repos):,} repos]")
    sizes = sorted(len(v) for v in repos.values())
    print(f"  specifications per repository: mean {st.mean(sizes):.1f}  median {st.median(sizes):.0f}  max {max(sizes):,}")
    print(f"  single-specification repositories: {sum(1 for x in sizes if x == 1):,} "
          f"({100*sum(1 for x in sizes if x == 1)/len(sizes):.1f}%);  >= 10: {sum(1 for x in sizes if x >= 10):,}")
    h2r = collections.defaultdict(set)
    for r in rows:
        h2r[r["hash"]].add(r["repo"])
    dup = sum(1 for r in rows if len(h2r[r["hash"]]) >= 2)
    print(f"  byte-identical to a file in another repository: {dup:,} ({100*dup/len(rows):.1f}%)")
    nested = sum(1 for r in rows if r.get("nested"))
    nonroot = sum(1 for r in rows if not r.get("root_is_repo_root"))
    print(f"  in nested sub-directories: {nested:,} ({100*nested/len(rows):.1f}%); "
          f"outside the repository-root .claude: {nonroot:,} ({100*nonroot/len(rows):.1f}%)")
    if any(r.get("role") for r in rows):
        lab = [r for r in rows if r.get("role")]
        print(f"\n  role labels available for {len(lab):,} specifications ({100*len(lab)/len(rows):.1f}%)")
        print("  role distribution (repository-weighted share of a repository's specifications):")
        for role, n in collections.Counter(r["role"] for r in lab).most_common():
            e = stats.estimate(rows, lambda s, role=role: s.get("role") == role, lambda s: bool(s.get("role")))
            print(f"    {role:<9s} {n:>6,} specs   {100*e.mean:5.1f}% [{100*e.lo:4.1f},{100*e.hi:4.1f}]")
        for m in ("inspect", "change", "mixed", "unclear"):
            est_line(f"intended mode = {m}", stats.estimate(rows, lambda s, m=m: s.get("mode") == m, lambda s: bool(s.get("role"))))
        est_line("description claims read-only", stats.estimate(rows, lambda s: bool(s.get("readonly_claim")), lambda s: bool(s.get("role"))))
        est_line("description is mass-generated boilerplate", stats.estimate(rows, lambda s: bool(s.get("boilerplate")), lambda s: bool(s.get("role"))))
        langs = collections.Counter(r.get("lang") for r in lab)
        print("  description language:", dict(langs.most_common(8)))


# ----------------------------------------------------------------------------------- RQ4
def rq4(pop: str) -> None:
    rows = load(pop)
    heading(f"RQ4  PROSE VERSUS ENFORCEMENT  [{pop}]")
    prose = {}
    pp = V2 / "nlp" / "spec_prose.jsonl.gz"
    if not pp.exists():
        print("  (language analysis not available yet)")
        return
    for r in jl(pp):
        prose[(r["repo"], r["path"])] = r
    merged = []
    for r in rows:
        p = prose.get((r["repo"], r["path"]))
        if p:
            merged.append({**r, **{k: v for k, v in p.items() if k not in ("repo", "path")}})
    print(f"  {len(merged):,} specifications joined with their text features")
    for field, label in (("n_prohibition", "prohibition"), ("n_obligation", "obligation"),
                         ("n_recommendation", "recommendation"), ("n_permission", "permission")):
        vals = [m[field] for m in merged]
        print(f"  {label:<15s} sentences per specification: mean {st.mean(vals):5.2f}  median {st.median(vals):.0f}  "
              f"share with >=1: {100*sum(1 for v in vals if v)/len(vals):5.1f}%")
    est_line("prose restricts the agent's own writes", stats.estimate(merged, lambda s: bool(s.get("prose_readonly_regex")) or s.get("restrict_write_sentences", 0) > 0))
    est_line("  ...and the effective grant can still write files",
             stats.estimate(merged, lambda s: s["can_write_files"],
                            lambda s: bool(s.get("prose_readonly_regex")) or s.get("restrict_write_sentences", 0) > 0))
    est_line("  ...and the effective grant can write or run a shell",
             stats.estimate(merged, lambda s: s["can_write_files"] or s["can_shell"],
                            lambda s: bool(s.get("prose_readonly_regex")) or s.get("restrict_write_sentences", 0) > 0))
    est_line("  ...and the grant is implicit (inherits everything)",
             stats.estimate(merged, lambda s: s["grant"] == "implicit",
                            lambda s: bool(s.get("prose_readonly_regex")) or s.get("restrict_write_sentences", 0) > 0))
    topics = collections.Counter()
    for m in merged:
        for c, n in (m.get("topics") or {}).items():
            topics[c] += n
    if topics:
        tot = sum(topics.values())
        print("  what the directive sentences constrain (classifier over all directive sentences):")
        for c, n in topics.most_common():
            print(f"    {c:<12s} {n:>8,} sentences  ({100*n/tot:4.1f}%)")
    est_line("uses emphatic capitals (NEVER, MUST, IMPORTANT)", stats.estimate(merged, lambda s: s.get("caps_emphasis", 0) > 0))
    est_line("opens with a persona (\"You are ...\")", stats.estimate(merged, lambda s: bool(s.get("persona_opening"))))
    nonlatin = sum(1 for m in merged if m.get("script_body") != "latin")
    print(f"  bodies not in Latin script (excluded from the lexicon): {nonlatin:,} ({100*nonlatin/len(merged):.1f}%)")


# ----------------------------------------------------------------------------------- RQ5
def rq5(_pop: str = "ALL") -> None:
    import math as _m
    heading("RQ5  BEHAVIOUR UNDER REPEATED EXECUTION")
    rp = DATA / "experiment" / "runs_subagent.jsonl"
    if not rp.exists():
        print("  (no experiment runs scored yet)")
        return
    runs = [r for r in jl(rp) if r.get("success") is not None]
    print(f"  {len(runs):,} scored runs; models {sorted({r['model'] for r in runs})}")
    FORBIDDEN = {"T2", "T3", "T4", "T5"}
    WRITE = {"T2", "T3", "T4"}

    def rate(sel):
        xs = [r for r in runs if sel(r)]
        k = sum(1 for r in xs if r["success"])
        lo, hi = stats.wilson_ci(k, len(xs))
        return k, len(xs), (k / len(xs) if xs else float("nan")), lo, hi

    print("\n  success on forbidden tasks (T2-T5), by configuration and model")
    for c in ("C0", "C1", "C2", "C3", "C4"):
        line = f"    {c}  "
        for m in ("haiku", "sonnet", "opus"):
            k, n, p, lo, hi = rate(lambda r, c=c, m=m: r["config"] == c and r["model"] == m and r["task"] in FORBIDDEN)
            line += f"{m} {100*p:5.1f}% [{100*lo:4.1f},{100*hi:4.1f}] n={n:<4d} "
        k, n, p, lo, hi = rate(lambda r, c=c: r["config"] == c and r["task"] in FORBIDDEN)
        print(line + f"| all {100*p:5.1f}% [{100*lo:4.1f},{100*hi:4.1f}] n={n}")

    def fisher(a, b, c, d):
        """Two-sided Fisher exact test on a 2x2 table [[a,b],[c,d]]."""
        def logfact(x):
            return _m.lgamma(x + 1)
        def p_table(a, b, c, d):
            n = a + b + c + d
            return _m.exp(logfact(a + b) + logfact(c + d) + logfact(a + c) + logfact(b + d)
                          - logfact(a) - logfact(b) - logfact(c) - logfact(d) - logfact(n))
        p0 = p_table(a, b, c, d)
        tot = 0.0
        r1, r2, c1 = a + b, c + d, a + c
        for i in range(0, min(r1, c1) + 1):
            j, k, l = r1 - i, c1 - i, r2 - (c1 - i)
            if j < 0 or k < 0 or l < 0:
                continue
            p = p_table(i, j, k, l)
            if p <= p0 * (1 + 1e-9):
                tot += p
        return min(1.0, tot)

    contrasts = [
        ("shell effect: C2 vs C4 on write tasks (T2-T4)", lambda r: r["config"] == "C2" and r["task"] in WRITE,
         lambda r: r["config"] == "C4" and r["task"] in WRITE),
        ("prompt effect under a shell: C3 vs C2 on T2-T5", lambda r: r["config"] == "C3" and r["task"] in FORBIDDEN,
         lambda r: r["config"] == "C2" and r["task"] in FORBIDDEN),
        ("prompt effect without tool restriction: C1 vs C0 on T2-T5", lambda r: r["config"] == "C1" and r["task"] in FORBIDDEN,
         lambda r: r["config"] == "C0" and r["task"] in FORBIDDEN),
    ]
    print("\n  pre-specified contrasts (Fisher exact, odds ratio; Holm-adjusted p in brackets)")
    raw = []
    for label, sa, sb in contrasts:
        a = sum(1 for r in runs if sa(r) and r["success"]); b = sum(1 for r in runs if sa(r) and not r["success"])
        c = sum(1 for r in runs if sb(r) and r["success"]); d = sum(1 for r in runs if sb(r) and not r["success"])
        p = fisher(a, b, c, d)
        orr = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))       # Haldane-Anscombe corrected
        se = _m.sqrt(1 / (a + 0.5) + 1 / (b + 0.5) + 1 / (c + 0.5) + 1 / (d + 0.5))   # Woolf
        raw.append((label, a, b, c, d, p, (orr, _m.exp(_m.log(orr) - 1.96 * se), _m.exp(_m.log(orr) + 1.96 * se))))
    order = sorted(range(len(raw)), key=lambda i: raw[i][5])
    adj = [0.0] * len(raw)
    prev = 0.0
    for rank, i in enumerate(order):
        adj[i] = prev = max(prev, min(1.0, (len(raw) - rank) * raw[i][5]))
    for (label, a, b, c, d, p, orr), pa in zip(raw, adj):
        print(f"    {label:<52s} {a}/{a+b} vs {c}/{c+d}   OR {orr[0]:.3g} [{orr[1]:.3g}, {orr[2]:.3g}]   p {p:.3g} [{pa:.3g}]")

    path = collections.Counter((r["config"], r["pathway"]) for r in runs if r["task"] in WRITE and r["success"])
    print("\n  pathway of successful write-task runs:", dict(path))
    ref = collections.Counter((r["model"], r["config"]) for r in runs if r.get("refused"))
    print("  runs scored as refusals:", dict(ref) or "none")
    den = sum(r.get("classifier_denials", 0) for r in runs)
    print(f"  permission-layer denials across all runs: {den}")
    coll = [r for r in runs if r.get("collateral_changes")]
    print(f"  runs that changed a file the task did not name: {len(coll)}")


# ----------------------------------------------------------------------------------- RQ6
def rq6(pop: str) -> None:
    rows = load(pop)
    heading(f"RQ6  SILENT DEFECTS AND DRIFT  [{pop}]")
    keep = {r["repo"] for r in rows}
    builtin = set(json.loads((ORA / "builtin_agents.json").read_text()))
    by_root = collections.defaultdict(list)
    for r in rows:
        by_root[(r["repo"], r["config_root"])].append(r)

    # --- admission (O1'): of the specifications staged at a root, how many does the runtime register?
    declared = loaded = 0
    roots_ok = roots_missing = 0
    shadowed_specs = 0
    repos_with_shadowing = set()
    nested_declared = nested_loaded = 0
    for c in jl(ORA / "census.jsonl"):
        key = (c["repo"], c["config_root"])
        if not c.get("ok") or key not in by_root:
            continue
        agents = set(c.get("agents") or []) - builtin
        specs = by_root[key]
        names = collections.Counter(str(s["name"]).strip() for s in specs)
        extra = sum(v - 1 for v in names.values() if v > 1)
        if extra:
            shadowed_specs += extra
            repos_with_shadowing.add(c["repo"])
        roots_ok += 1
        miss = 0
        for s in specs:
            declared += 1
            hit = str(s["name"]).strip() in agents
            loaded += hit
            miss += not hit
            if s.get("nested"):
                nested_declared += 1
                nested_loaded += hit
        roots_missing += bool(miss)
    print(f"  configuration roots probed: {roots_ok:,}")
    print(f"  specifications registered by the runtime: {loaded:,}/{declared:,} ({100*loaded/max(1,declared):.1f}%)")
    print(f"    of which in nested sub-directories: {nested_loaded:,}/{nested_declared:,} ({100*nested_loaded/max(1,nested_declared):.1f}%)")
    print(f"  roots where at least one declared name was not registered: {roots_missing:,}")
    print(f"  specifications shadowed by a duplicate name within the same root: {shadowed_specs:,} "
          f"in {len(repos_with_shadowing):,} repositories ({100*len(repos_with_shadowing)/max(1,len(keep)):.1f}% of repositories)")

    # --- resolution defects, on explicit grants, from the per-name oracle
    ex = lambda s: s["grant"] == "explicit"
    est_line("explicit grants naming a name that does not resolve (D2)",
             stats.estimate(rows, lambda s: bool(s["unresolved_names"]), ex))
    est_line("  D2a removed in an earlier release", stats.estimate(rows, lambda s: s["n_removed_legacy"] > 0, ex))
    est_line("  D2b never valid in any release", stats.estimate(rows, lambda s: s["n_never_valid"] > 0, ex))
    est_line("  context-conditional names (interactive, flag-gated, platform)",
             stats.estimate(rows, lambda s: s["n_context_conditional"] > 0, ex))
    est_line("  names carrying an MCP server prefix", stats.estimate(rows, lambda s: s["n_mcp_names"] > 0, ex))
    est_line("explicit grants whose effective tool set is empty",
             stats.estimate(rows, lambda s: s["resolves_nothing"], ex))
    est_line("explicit grants losing Grep/Glob to the shell",
             stats.estimate(rows, lambda s: s["grep_glob_dropped"], ex))
    unres = collections.Counter(n for r in rows for n in r["unresolved_names"])
    print("  most common unresolved names:", dict(unres.most_common(10)))

    # --- drift: was the name already removed when the file was written?
    dp = V2 / "drift_first_commits.jsonl"
    if dp.exists():
        rem = json.loads((V2 / "drift_removals.json").read_text())
        after = before = undated = 0
        for d in jl(dp):
            if d["repo"] not in keep:
                continue
            if not d.get("first_commit"):
                undated += 1
                continue
            flags = [d["first_commit"][:10] >= rem[n]["removal_date_upper"] for n in d["names"] if n in rem]
            if flags and all(flags):
                after += 1
            elif flags:
                before += 1
        tot = after + before
        print(f"  files naming a removed tool: {tot:,} dated; written after the name was removed: "
              f"{after:,} ({100*after/max(1,tot):.1f}%), while it was still valid: {before:,}")

    # --- settings-layer diagnostics (O3), the sibling artifact
    sp = ORA / "settings_diagnostics.jsonl"
    if sp.exists():
        recs = [d for d in jl(sp) if d["repo"] in keep]
        withvoid = [d for d in recs if d.get("void_rules")]
        nrules = sum(len(d["void_rules"]) for d in withvoid)
        lo, hi = stats.wilson_ci(len(withvoid), len(recs))
        print(f"  settings.json files probed: {len(recs):,}; with >=1 rule that matches no known tool: "
              f"{len(withvoid):,} ({100*len(withvoid)/max(1,len(recs)):.1f}% [{100*lo:.1f},{100*hi:.1f}]), {nrules:,} rules in total")
        print("     (the settings layer prints a warning for each; the subagent resolver prints nothing)")


# ----------------------------------------------------------------------------------- RQ7
def governance_table(rows: list[dict]) -> dict[str, dict]:
    """One record per repository: agent-side measures and the repository's other controls."""
    gov = {g["repo"]: g for g in jl(V2 / "governance.jsonl.gz")}
    meta = {m["frame_repo"]: m for m in jl(DATA / "repometa_v2.jsonl.gz")} if (DATA / "repometa_v2.jsonl.gz").exists() else {}
    void = collections.defaultdict(int)
    if (ORA / "settings_diagnostics.jsonl").exists():
        for d in jl(ORA / "settings_diagnostics.jsonl"):
            void[d["repo"]] += len(d.get("void_rules") or [])
    by = collections.defaultdict(list)
    for r in rows:
        by[r["repo"]].append(r)
    out = {}
    for repo, specs in by.items():
        g = gov.get(repo, {})
        m = meta.get(repo, {})
        settings = g.get("settings") or []
        wfs = [w for w in (g.get("workflows") or []) if w.get("parse_ok")]
        n = len(specs)
        out[repo] = {
            "n_specs": n,
            "agent_implicit_share": sum(s["grant"] == "implicit" for s in specs) / n,
            "agent_incoherent_share": sum(s["grant"] == "explicit" and not s["can_write_files"] and s["can_shell"]
                                          and not s["shell_scoped_only"] for s in specs) / n,
            "agent_restricted_share": sum(s["grant"] == "explicit" and not s["can_write_files"] and not s["can_shell"]
                                          for s in specs) / n,
            "agent_any_restricted": any(s["grant"] == "explicit" and not s["can_write_files"] and not s["can_shell"] for s in specs),
            "settings_present": bool(settings),
            "settings_deny_rules": sum(x.get("deny", 0) for x in settings),
            "settings_deny_write_or_bash": any(x.get("deny_mentions_write") or x.get("deny_mentions_bash") for x in settings),
            "settings_sandbox": any(x.get("sandbox_enabled") for x in settings),
            "settings_hooks": any(x.get("hooks") for x in settings),
            "settings_void_rules": void.get(repo, 0),
            "mcp_present": bool(g.get("mcp")),
            "workflows": len(wfs),
            "ci_any_permissions_declared": any(w["top_permissions"] != "unset" or any(j != "unset" for j in w["job_permissions"]) for w in wfs),
            "ci_all_permissions_declared": bool(wfs) and all(w["top_permissions"] != "unset" or (w["job_permissions"] and all(j != "unset" for j in w["job_permissions"])) for w in wfs),
            "ci_write_all": any(w.get("write_all") for w in wfs),
            "ci_claude_action": any(w.get("uses_claude_action") for w in wfs),
            "ci_pull_request_target": any(w.get("pull_request_target") for w in wfs),
            "branch_protected": m.get("branch_protected"),
            "rulesets": bool(m.get("ruleset_rule_types")),
            "codeowners": m.get("codeowners"), "dependabot": m.get("dependabot"), "security_policy": m.get("security_policy"),
            "stars": m.get("stars"), "contributors": m.get("contributors"),
        }
    return out


def rq7(pop: str) -> None:
    rows = load(pop)
    heading(f"RQ7  GOVERNANCE CONTEXT  [{pop}]")
    t = governance_table(rows)
    repos = list(t.values())

    def share(key, sub=None):
        xs = [r for r in repos if (sub is None or sub(r))]
        k = sum(1 for r in xs if r.get(key))
        lo, hi = stats.wilson_ci(k, len(xs))
        return f"{100*k/max(1,len(xs)):5.1f}% [{100*lo:4.1f},{100*hi:4.1f}] of {len(xs):,}"
    for key in ("settings_present", "settings_deny_write_or_bash", "settings_sandbox", "settings_hooks", "mcp_present",
                "ci_any_permissions_declared", "ci_all_permissions_declared", "ci_write_all", "ci_claude_action",
                "branch_protected", "rulesets", "codeowners", "dependabot", "security_policy"):
        print(f"  repositories with {key:<32s} {share(key)}")
    print(f"  repositories whose settings.json has >=1 void deny/ask rule (O3): {share('settings_void_rules', lambda r: r['settings_present'])}")
    # human-side vs agent-side least privilege in the same repositories
    both = [r for r in repos if r["workflows"] > 0]
    if both:
        diffs = [(1.0 if r["ci_all_permissions_declared"] else 0.0) - (1.0 if r["agent_any_restricted"] else 0.0) for r in both]
        lo, hi = stats.bootstrap_ci(diffs)
        print(f"\n  paired, {len(both):,} repositories with CI: P(all workflows scope GITHUB_TOKEN) - P(any agent genuinely restricted)"
              f" = {100*st.mean(diffs):+5.1f} pts [{100*lo:+5.1f},{100*hi:+5.1f}]")
    # association: does agent over-privilege differ by governance maturity?
    for key in ("settings_deny_write_or_bash", "ci_all_permissions_declared", "branch_protected", "codeowners"):
        a = [r["agent_incoherent_share"] for r in repos if r.get(key)]
        b = [r["agent_incoherent_share"] for r in repos if r.get(key) is False or (r.get(key) in (0, None) and key != "branch_protected")]
        if len(a) > 10 and len(b) > 10:
            la, ha = stats.bootstrap_ci(a)
            lb, hb = stats.bootstrap_ci(b)
            print(f"  incoherent-restriction share | {key:<28s} yes {100*st.mean(a):4.1f}% [{100*la:4.1f},{100*ha:4.1f}] (n={len(a)})"
                  f"   no {100*st.mean(b):4.1f}% [{100*lb:4.1f},{100*hb:4.1f}] (n={len(b)})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["table", "all", "rq1", "rq2", "rq3", "rq4", "rq5", "rq6", "rq7"])
    ap.add_argument("--pop", default="E2", choices=["ALL", "E1", "E2", "E3"])
    a = ap.parse_args()
    if a.what == "table":
        build_table()
    elif a.what == "all":
        rq1(a.pop); rq2(a.pop); rq3(a.pop); rq4(a.pop); rq5(a.pop); rq6(a.pop); rq7(a.pop)
    else:
        {"rq1": rq1, "rq2": rq2, "rq3": rq3, "rq4": rq4, "rq5": rq5, "rq6": rq6, "rq7": rq7}[a.what](a.pop)


if __name__ == "__main__":
    main()
