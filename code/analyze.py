"""Reproduce every number the paper reports.

    python3 code/analyze.py

Prints the results in the order the paper presents them. All prevalence figures are
repository-weighted with a percentile bootstrap over repositories; see ``stats``.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics as st
from pathlib import Path

import parsing
import roles
import stats

DEFAULT_VOCAB = Path(__file__).resolve().parent.parent / "data" / "tool_vocab.json"


def heading(text: str) -> None:
    print("\n" + "=" * 84 + f"\n{text}\n" + "=" * 84)


def run(corpus: Path, vocab_path: Path, meta_path: Path | None = None,
        oracle_path: Path | None = None) -> None:
    vocabulary = set(json.loads(Path(vocab_path).read_text())["valid"])
    records = parsing.load_records(corpus)
    specs = roles.label([r for r in records if parsing.is_specification(r)])
    grouped = stats.by_repository(specs)

    known = lambda t: parsing.is_known_tool(t, vocabulary)
    explicit = parsing.declares_tools

    # ---------------------------------------------------------------- corpus
    heading("CORPUS")
    counts = collections.Counter(s["repo"] for s in specs)
    top = counts.most_common()
    print(f"files under .claude/agents/**.md : {len(records):,}")
    print(f"specifications                   : {len(specs):,} in {len(grouped):,} repositories")
    print(f"share of files that are specs    : {100*len(specs)/len(records):.1f}%")
    print(f"concentration                    : top repo {100*top[0][1]/len(specs):.1f}%, "
          f"top 10 {100*sum(n for _, n in top[:10])/len(specs):.1f}%")

    # ------------------------------------------------- capability and omission
    heading("CAPABILITY")
    omits = stats.estimate(specs, lambda s: s.get("tools") is None)
    print(f"  omits `tools:` (inherits full pool)   {omits}")
    print(f"  {'':38s} omission is the MOST permissive choice, not a neutral default")
    read_only = stats.estimate(
        specs,
        lambda s: not ({parsing.base_tool(t) for t in s["tools"]} & parsing.WRITE_SETS["primary"]),
        explicit)
    print(f"  read-only (explicit lists only)       {read_only}")

    heading("CAPABILITY BY ROLE  (unconditional: omission counts as holding it)")
    print(f"  {'role':<13s} {'specs':>7s} {'can write files':>24s} {'write or shell':>24s}")
    for role, _ in roles.STRICT_PATTERNS:
        group = [s for s in specs if s["role_strict"] == role]
        if len(group) < 100:
            continue
        fw = stats.estimate(specs, lambda s: parsing.grants_capability(s, "narrow"),
                            lambda s, r=role: s["role_strict"] == r)
        pr = stats.estimate(specs, lambda s: parsing.grants_capability(s, "primary"),
                            lambda s, r=role: s["role_strict"] == r)
        print(f"  {role:<13s} {len(group):>7,} "
              f"{100*fw.mean:>16.1f}% [{100*fw.lo:.0f},{100*fw.hi:.0f}]"
              f"{100*pr.mean:>16.1f}% [{100*pr.lo:.0f},{100*pr.hi:.0f}]")

    for label, wset in (("file-write", "narrow"), ("write-or-shell", "primary")):
        c = stats.paired_contrast(
            specs,
            lambda s: s["role_strict"] in roles.INSPECTION_ROLES,
            lambda s: s["role_strict"] in roles.CHANGE_ROLES,
            lambda s, w=wset: parsing.grants_capability(s, w))
        if c:
            flag = "  <-- CI excludes 0" if c["excludes_zero"] else ""
            print(f"  paired contrast {label:<15s} {100*c['difference']:+5.1f} pts "
                  f"CI [{100*c['lo']:+5.1f},{100*c['hi']:+5.1f}]  n={c['n_repos']} repos{flag}")

    # ------------------------------------------------------------- mechanism
    heading("MECHANISM: how the restriction is undone")
    inspection = [s for s in specs if s["role_strict"] in roles.INSPECTION_ROLES and explicit(s)]
    writes = lambda s: bool({parsing.base_tool(t) for t in s["tools"]} & parsing.WRITE_SETS["narrow"])
    has_bash = lambda s: "Bash" in {parsing.base_tool(t) for t in s["tools"]}
    withheld = [s for s in inspection if not writes(s)]
    with_bash = [s for s in withheld if has_bash(s)]
    bash_granted = [s for s in inspection if has_bash(s)]
    scoped = [s for s in bash_granted if any(t.startswith("Bash(") for t in s["tools"])]
    print(f"  inspection specs with an explicit list : {len(inspection):,}")
    print(f"  withhold file-writing tools            : {len(withheld):,} "
          f"({100*len(withheld)/len(inspection):.1f}%)")
    print(f"  ...of those, granted unrestricted Bash : {len(with_bash):,} "
          f"({100*len(with_bash)/len(withheld):.1f}%)")
    print(f"  genuinely read-only                    : {len(withheld)-len(with_bash):,} "
          f"({100*(len(withheld)-len(with_bash))/len(inspection):.1f}%)")
    print(f"  Bash grants scoped as Bash(...)        : {len(scoped):,}/{len(bash_granted):,} "
          f"({100*len(scoped)/len(bash_granted):.1f}%)")

    # ------------------------------------------------------- declared fields
    heading("WHAT DEVELOPERS POPULATE")
    fields = [("model", False), ("color", True), ("memory", False), ("maxTurns", False),
              ("permissionMode", False), ("hooks", False), ("disallowedTools", False),
              ("isolation", False), ("background", False)]
    for field, cosmetic in fields:
        pred = ((lambda s: bool(s.get("has_hooks"))) if field == "hooks"
                else (lambda s, f=field: s.get(f) is not None))
        est = stats.estimate(specs, pred)
        tag = "[cosmetic]" if cosmetic else ""
        label = f"declares `{field}` {tag}".rstrip()
        print(f"  {label:<36s} {est}")

    # -------------------------------------------------------------- defects
    heading("DEFECT CENSUS")
    checks = [
        ("D2  names an unrecognised tool",
         lambda s: any(not known(t) for t in s["tools"]), explicit),
        ("D2a   ...a removed legacy tool",
         lambda s: any((not known(t)) and parsing.base_tool(t) in parsing.LEGACY_TOOLS
                       for t in s["tools"]), explicit),
        ("D2b   ...a never-valid name",
         lambda s: any((not known(t)) and parsing.base_tool(t) not in parsing.LEGACY_TOOLS
                       for t in s["tools"]), explicit),
        ("D3  names no recognised tool at all",
         lambda s: not any(known(t) for t in s["tools"]), explicit),
        ("D4  sets permissionMode",
         lambda s: s.get("permissionMode") is not None, None),
        ("D5  unrecognised model value",
         lambda s: not re.match(r"^(opus|sonnet|haiku|fable|inherit|claude-)",
                                str(s.get("model")), re.I),
         lambda s: s.get("model") is not None),
        ("    uses a non-schema field",
         lambda s: bool(set(s.get("fm_keys", [])) - parsing.SCHEMA_FIELDS), None),
    ]
    for label, pred, pop in checks:
        est = stats.estimate(specs, pred, pop)
        if est:
            print(f"  {label:<36s} {est}")

    shadowed = repos_affected = 0
    for records_in_repo in grouped.values():
        names = collections.Counter(str(s.get("name")).strip() for s in records_in_repo)
        extra = sum(v - 1 for v in names.values() if v > 1)
        if extra:
            shadowed += extra
            repos_affected += 1
    print(f"  {'D6  shadowed by a duplicate name':<36s} {shadowed:,} specs in {repos_affected} repos "
          f"({100*repos_affected/len(grouped):.1f}% of repositories)")

    unknown = collections.Counter(parsing.base_tool(t) for s in specs if explicit(s)
                                  for t in s["tools"] if not known(t))
    print("\n  most common unrecognised tool names:", dict(unknown.most_common(8)))

    # ----------------------------------------------------------- clustering
    heading("CLUSTERING")
    groups = [[1 if parsing.grants_capability(s, "primary") else 0
               for s in records_in_repo if explicit(s)]
              for records_in_repo in grouped.values()]
    icc = stats.intraclass_correlation(groups)
    if icc:
        print(f"  write/exec outcome: {icc['n_specs']:,} specs in {icc['n_repos']:,} repositories")
        print(f"  ICC {icc['icc']:.3f}   design effect {icc['design_effect']:.2f}   "
              f"effective n {icc['effective_n']:.0f} (not {icc['n_specs']:,})")
        print("  => treating specifications as independent would understate uncertainty ~6-fold")

    robustness(records, specs, grouped, vocabulary, meta_path, oracle_path)


def robustness(records, specs, grouped, vocabulary, meta_path, oracle_path) -> None:
    """Every remaining number the paper quotes: team and grant sizes, non-schema fields,
    unrecognised names by repository, strata, the deduplicated sample, truncation checks,
    the O1 reconciliation, cross-repository duplication and adoption timing."""
    known = lambda t: parsing.is_known_tool(t, vocabulary)
    explicit = parsing.declares_tools

    heading("TEAM SIZE AND GRANT SIZE")
    sizes = sorted(len(g) for g in grouped.values())
    single = sum(1 for x in sizes if x == 1)
    print(f"  specifications per repository: mean {st.mean(sizes):.1f}   median {st.median(sizes):.0f}   max {max(sizes):,}")
    print(f"  single-specification repositories: {single:,} ({100*single/len(sizes):.1f}%)   "
          f"repositories with >=100 specifications: {sum(1 for x in sizes if x >= 100)}")
    grants = [len(s["tools"]) for s in specs if explicit(s)]
    print(f"  explicit tool lists: {len(grants):,}   median grant {st.median(grants):.0f} tools   mean {st.mean(grants):.2f}")

    heading("NON-SCHEMA FIELDS AND THE allowed-tools NEAR MISS")
    occ, rep = collections.Counter(), collections.defaultdict(set)
    for s in specs:
        for k in set(s.get("fm_keys", [])) - parsing.SCHEMA_FIELDS:
            occ[k] += 1
            rep[k].add(s["repo"])
    print("  most common non-schema fields, by repositories using them (specifications in brackets):")
    for k in sorted(occ, key=lambda k: (-len(rep[k]), -occ[k]))[:10]:
        print(f"    {k:<16s} {len(rep[k]):>4d} repos   ({occ[k]:>6,} specs)")
    near = lambda s: s.get("tools_raw") is None and any(k in parsing.NEAR_MISS_FIELDS for k in s.get("fm_keys", []))
    nm = [s for s in specs if near(s)]
    est = stats.estimate(specs, near)
    top5 = sum(n for _, n in collections.Counter(s["repo"] for s in nm).most_common(5))
    print(f"  near-miss field present and `tools:` omitted: {len(nm):,} specs "
          f"({100*len(nm)/len(specs):.1f}% pooled) in {len({s['repo'] for s in nm})} repos; "
          f"repository-weighted {100*est.mean:.1f}% [{100*est.lo:.1f},{100*est.hi:.1f}]; "
          f"the five largest of those repos hold {top5:,} of them")

    heading("UNRECOGNISED TOOL NAMES  (repositories; occurrences)")
    u_occ, u_rep = collections.Counter(), collections.defaultdict(set)
    for s in specs:
        if not explicit(s):
            continue
        for t in s["tools"]:
            if not known(t):
                b = parsing.base_tool(t)
                u_occ[b] += 1
                u_rep[b].add(s["repo"])
    legacy = [b for b in sorted(u_occ, key=lambda b: -len(u_rep[b])) if b in parsing.LEGACY_TOOLS][:6]
    never = [b for b in sorted(u_occ, key=lambda b: -len(u_rep[b])) if b not in parsing.LEGACY_TOOLS][:8]
    print("  D2a removed legacy names :", ", ".join(f"{b} ({len(u_rep[b])}; {u_occ[b]:,})" for b in legacy))
    print("  D2b never-valid names    :", ", ".join(f"{b} ({len(u_rep[b])}; {u_occ[b]:,})" for b in never))

    if meta_path and Path(meta_path).exists():
        heading("ROBUSTNESS: REPOSITORY STRATA  (omits tools: | grants Bash among explicit lists)")
        meta = {m["repo"]: m for m in parsing.iter_jsonl(meta_path)}
        stars = [meta[r]["stars"] for r in grouped if r in meta]
        print(f"  metadata for {len(stars):,} repos: median stars {st.median(stars):.0f}, "
              f"{100*sum(1 for x in stars if x == 0)/len(stars):.1f}% with no stars, "
              f"{sum(1 for r in grouped if r in meta and meta[r]['license']):,} licensed, "
              f"{sum(1 for r in grouped if r in meta and meta[r]['is_fork'])} forks")
        omit = lambda s: s.get("tools") is None
        bash = lambda s: "Bash" in {parsing.base_tool(t) for t in s["tools"]}
        strata = [("all repositories", lambda r: True),
                  (">=1 star", lambda r: r in meta and meta[r]["stars"] >= 1),
                  (">=10 stars", lambda r: r in meta and meta[r]["stars"] >= 10),
                  (">=50 stars", lambda r: r in meta and meta[r]["stars"] >= 50),
                  ("licensed, non-fork", lambda r: r in meta and meta[r]["license"] and not meta[r]["is_fork"]),
                  ("excluding repos >=100 specs", lambda r: len(grouped[r]) < 100)]
        for name, keep in strata:
            sub = [s for s in specs if keep(s["repo"])]
            e1, e2 = stats.estimate(sub, omit), stats.estimate(sub, bash, explicit)
            print(f"  {name:<30s} repos {e1.n_repos:>5,}   omits {100*e1.mean:.1f}% [{100*e1.lo:.0f},{100*e1.hi:.0f}]"
                  f"   Bash {100*e2.mean:.1f}% [{100*e2.lo:.0f},{100*e2.hi:.0f}]")
        created = [meta[r]["created"][:7] for r in grouped if r in meta and meta[r].get("created")]
        recent = sum(1 for c in created if c >= "2025-03")
        print(f"  repositories created in the 18 months before collection (since 2025-03): "
              f"{recent:,} of {len(created):,} ({100*recent/len(created):.1f}%)")

    heading("ROBUSTNESS: AT MOST ONE SPECIFICATION PER REPOSITORY PER ROLE  (first in path order)")
    seen, dedup = set(), []
    for s in sorted(specs, key=lambda s: (s["repo"], s["path"])):
        if s["role_strict"] is None or (s["repo"], s["role_strict"]) in seen:
            continue
        seen.add((s["repo"], s["role_strict"]))
        dedup.append(s)
    print(f"  deduplicated sample: {len(dedup):,} specifications")
    for label, wset in (("file-write", "narrow"), ("write-or-shell", "primary")):
        c = stats.paired_contrast(dedup,
                                  lambda s: s["role_strict"] in roles.INSPECTION_ROLES,
                                  lambda s: s["role_strict"] in roles.CHANGE_ROLES,
                                  lambda s, w=wset: parsing.grants_capability(s, w))
        print(f"  paired contrast {label:<15s} {100*c['difference']:+5.1f} pts CI [{100*c['lo']:+5.1f},{100*c['hi']:+5.1f}]  n={c['n_repos']} repos")
    floor = min(stats.estimate(dedup, lambda s: parsing.grants_capability(s, "primary"),
                               lambda s, r=role: s["role_strict"] == r).mean
                for role, _ in roles.STRICT_PATTERNS)
    print(f"  lowest write-or-shell share across roles on this sample: {100*floor:.1f}%")
    icc = stats.intraclass_correlation([[1 if parsing.grants_capability(s, "primary") else 0
                                         for s in g if explicit(s)]
                                        for g in stats.by_repository(dedup).values()])
    print(f"  ICC {icc['icc']:.3f}   design effect {icc['design_effect']:.2f}  (was 6.34 on the full corpus)")

    heading("TRUNCATION CHECK: SPEARMAN CORRELATION WITH FILE SIZE")
    ex = [s for s in specs if explicit(s)]
    print(f"  bytes ~ number of tools granted (explicit lists): rho = {stats.spearman([s['bytes'] for s in ex], [len(s['tools']) for s in ex]):.2f}")
    print(f"  bytes ~ omits `tools:` (all specifications)      : rho = {stats.spearman([s['bytes'] for s in specs], [1 if s.get('tools') is None else 0 for s in specs]):.3f}")

    if oracle_path and Path(oracle_path).exists():
        heading("O1 ACCEPTANCE ORACLE: RECONCILIATION WITH THE PARSER")
        by_repo_all = collections.defaultdict(list)
        for r in records:
            by_repo_all[r["repo"]].append(r)
        probes = list(parsing.iter_jsonl(oracle_path))
        declared = accepted = nested_declared = nested_accepted = 0
        extra_names = extra_repos = 0
        covered = True
        missing = collections.Counter()
        for o in probes:
            acc = set(o["accepted"])
            recs_here = by_repo_all.get(o["repo"], [])
            extra = acc - set(o["declared"])
            if extra:
                extra_names += len(extra)
                extra_repos += 1
                unparsed = sum(1 for r in recs_here if r.get("fm_error") or not r.get("name"))
                covered &= unparsed >= len(extra)
            for r in recs_here:
                if not (parsing.is_specification(r) and isinstance(r.get("name"), str)):
                    continue
                nested = "/" in r["path"].split(".claude/agents/", 1)[-1]
                ok = r["name"].strip() in acc
                declared += 1; accepted += ok
                if nested:
                    nested_declared += 1; nested_accepted += ok
                if not ok:
                    missing[o["repo"]] += 1
        print(f"  repositories probed: {len(probes):,}")
        print(f"  names listed by the tool but absent from our declared set: {extra_names:,} in {extra_repos} repos; "
              f"in every such repo the count is covered by files our parser could not read: {covered}")
        print(f"  parseable specifications listed by the tool: {accepted:,}/{declared:,} ({100*accepted/declared:.1f}%)")
        print(f"    top-level {accepted-nested_accepted:,}/{declared-nested_declared:,} "
              f"({100*(accepted-nested_accepted)/(declared-nested_declared):.1f}%)   "
              f"nested sub-directories {nested_accepted:,}/{nested_declared:,} ({100*nested_accepted/max(1,nested_declared):.1f}%)")
        print(f"  not listed: {sum(missing.values())} specifications in {len(missing)} repos "
              f"(largest: {missing.most_common(3)})")

    heading("CROSS-REPOSITORY DUPLICATION")
    h2r = collections.defaultdict(set)
    for s in specs:
        h2r[s["hash"]].add(s["repo"])
    dup = sum(1 for s in specs if len(h2r[s["hash"]]) >= 2)
    print(f"  specifications byte-identical to a file in another repository: {dup:,} ({100*dup/len(specs):.1f}%)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path,
                    default=Path(__file__).resolve().parent.parent / "data" / "agents.jsonl.gz")
    ap.add_argument("--vocab", default=DEFAULT_VOCAB, type=Path)
    data = Path(__file__).resolve().parent.parent / "data"
    ap.add_argument("--meta", type=Path, default=data / "repometa.jsonl.gz",
                    help="repository metadata (stars, licence, creation date) for the strata")
    ap.add_argument("--oracle", type=Path, default=data / "oracle_agents.jsonl.gz",
                    help="O1 acceptance-oracle results for the reconciliation")
    args = ap.parse_args()
    run(args.corpus, args.vocab, args.meta, args.oracle)


if __name__ == "__main__":
    main()
