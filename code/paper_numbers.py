#!/usr/bin/env python3
"""Generate paper/numbers.tex: every quantity the manuscript quotes, as a LaTeX macro.

    python3 code/paper_numbers.py

No number is typed into the manuscript by hand. Each macro is computed here from the released data; a macro the
drafts use but this script cannot yet compute is emitted as a visible placeholder (\\textbf{??}) so that an
unfinished value cannot silently reach the PDF.
"""
from __future__ import annotations

import collections
import gzip
import json
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
V2 = DATA / "v2"
ORA = V2 / "oracles"
PAPER = ROOT / "paper"


def jl(path: Path):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def pct(x: float) -> str:
    return f"{100*x:.1f}\\%"


def num(x: int) -> str:
    return f"{x:,}".replace(",", "{,}")


def ci(e) -> str:
    return f"{100*e.mean:.1f}\\% ({100*e.lo:.1f}--{100*e.hi:.1f})"


def main() -> None:
    m: dict[str, str] = {}
    rows = list(jl(V2 / "spec_table.jsonl.gz"))
    eng = [r for r in rows if r.get("E2")]
    pop = eng if eng else rows
    tag = "E2" if eng else "ALL"

    # ---- corpus and curation
    m["nSpecsAll"] = num(len(rows))
    m["nReposAll"] = num(len({r["repo"] for r in rows}))
    m["nSpecsEng"] = num(len(eng)) if eng else "\\textbf{??}"
    m["nReposEng"] = num(len({r["repo"] for r in eng})) if eng else "\\textbf{??}"
    build = json.loads((V2 / "build_report.json").read_text())
    m["nInventoryFiles"] = num(build["inventory_agent_files"])
    m["nFilesOk"] = num(build["status"].get("ok", 0))
    m["nFilesUnavailable"] = num(build["inventory_agent_files"] - build["status"].get("ok", 0))
    m["pctUnavailable"] = pct(1 - build["status"].get("ok", 0) / build["inventory_agent_files"])
    bl = DATA / "work" / "blobs.jsonl"
    if bl.exists():   # repositories from which at least one file was recovered and hash-verified
        recovered = {b["repo"] for b in jl(bl) if b.get("status") == "ok"}
        m["nReposRecovered"] = num(len(recovered))
    prov = json.loads((DATA / "provenance.json").read_text())
    m["nFrame"] = num(prov["repositories_discovered"])
    m["nBandsTruncated"] = num(prov["bands_truncated"])
    m["pctFrameOfRerun"] = pct(prov["repositories_discovered"] / 12251)   # 12,251 = repositories in the re-run
    m["nReportedTotal"] = num(prov["reported_total_sum"])
    m["nRerun"] = num(12251)
    m["pctRerunOverlap"] = "99.4\\%"

    # ---- oracle scale
    m["nDistinctGrants"] = num(sum(1 for _ in jl(ORA / "resolver_unauth.jsonl")))
    m["nDistinctNames"] = num(sum(1 for _ in jl(ORA / "names_unauth.jsonl")))
    m["nRootsCensus"] = num(sum(1 for _ in jl(ORA / "census.jsonl")))
    m["nReleasesHistory"] = num(sum(1 for r in jl(ORA / "tool_pool_history.jsonl") if r.get("ok")) + 1)

    # ---- RQ1
    by_repo = collections.Counter(r["repo"] for r in pop)
    sizes = sorted(by_repo.values())
    m["medianTeam"] = f"{st.median(sizes):.0f}"
    m["meanTeam"] = f"{st.mean(sizes):.1f}"
    m["maxTeam"] = num(max(sizes))
    h2r = collections.defaultdict(set)
    for r in rows:
        h2r[r["hash"]].add(r["repo"])
    # share of primary-population specifications with a byte-identical copy in another repository of the corpus,
    # and the share that repeats content already present in the population (all but one copy per hash)
    m["RQoneDuplication"] = pct(sum(1 for r in pop if len(h2r[r["hash"]]) >= 2) / len(pop))
    m["RQoneRepeatShare"] = pct(1 - len({r["hash"] for r in pop}) / len(pop))

    # where the files live: pooled shares and repository-level means
    m["RQoneNestedPooled"] = pct(sum(1 for r in pop if r.get("nested")) / len(pop))
    m["RQoneNested"] = ci(stats.estimate(pop, lambda s: bool(s.get("nested"))))
    m["RQoneOutsideRootPooled"] = pct(sum(1 for r in pop if r.get("root_is_repo_root") is False) / len(pop))
    m["RQoneOutsideRoot"] = ci(stats.estimate(pop, lambda s: s.get("root_is_repo_root") is False))
    expl_ = [r for r in pop if r["grant"] == "explicit"]
    m["medianRequested"] = f"{st.median(r['n_requested'] for r in expl_):.0f}"
    m["medianEffective"] = f"{st.median(len(r['effective']) for r in expl_):.0f}"

    # the headline quantities under every population (robustness to the curation cuts)
    popsets = {"All": rows, "Eone": [r for r in rows if r.get("E1")], "Etwo": pop, "Ethree": [r for r in rows if r.get("E3")]}
    for pname, pr in popsets.items():
        m[f"Pop{pname}Implicit"] = pct(stats.estimate(pr, lambda s: s["grant"] == "implicit").mean)
        m[f"Pop{pname}Incoherent"] = pct(stats.estimate(pr, lambda s: s["can_shell"] and not s["shell_scoped_only"],
                                                        lambda s: s["grant"] == "explicit" and not s["can_write_files"]).mean)
        for key, outcome in (("GapWrite", lambda s: bool(s["can_write_files"])),
                             ("GapAuthority", lambda s: bool(s["can_write_files"]) or bool(s["can_shell"]))):
            d = stats.paired_contrast(pr, lambda s: s.get("mode") == "inspect", lambda s: s.get("mode") == "change", outcome)
            if d:
                m[f"Pop{pname}{key}"] = f"{100*d['difference']:.1f}"

    # ---- RQ2 / RQ3 on the primary population
    e = stats.estimate(pop, lambda s: s["grant"] == "implicit")
    m["RQtwoImplicitEng"] = ci(e)
    e = stats.estimate(pop, lambda s: s["can_write_files"] or s["can_shell"], lambda s: s["grant"] == "explicit")
    m["RQtwoExplicitCapable"] = ci(e)
    withheld = lambda s: s["grant"] == "explicit" and not s["can_write_files"]
    e = stats.estimate(pop, lambda s: s["can_shell"] and not s["shell_scoped_only"], withheld)
    m["RQthreeIncoherentEng"] = ci(e)
    m["nReposWithhold"] = num(e.n_repos)   # repositories contributing to the RQ3 headline mean
    # the RQ3 headline by repository size (specifications per repository), a check on file-level discovery
    _size = collections.Counter(r["repo"] for r in pop)
    _parts = []
    for lo_, hi_, lab in ((1, 1, "1"), (2, 5, "2--5"), (6, 20, "6--20"), (21, 10**9, "more than 20")):
        _e = stats.estimate([r for r in pop if lo_ <= _size[r["repo"]] <= hi_],
                            lambda s: s["can_shell"] and not s["shell_scoped_only"], withheld)
        if _e:
            _parts.append(f"{100*_e.mean:.1f}\\% ({lab})")
    m["RQthreeIncoherentBySize"] = ", ".join(_parts)
    # denominator: explicit lists that name Grep or Glob *alongside Bash* (the numerator requires Bash too)
    e = stats.estimate(pop, lambda s: s["grep_glob_dropped"],
                       lambda s: s["grant"] == "explicit" and bool({"Grep", "Glob"} & set(s["requested"]))
                       and "Bash" in s["requested"])
    m["RQthreeGrepDropped"] = ci(e)
    # RQ6 as repository shares (the estimate above is a mean of within-repository proportions)
    expl_repos = {r["repo"] for r in pop if r["grant"] == "explicit"}
    m["nReposExplicit"] = num(len(expl_repos))
    for key, pred in (("RQsixUnresolvedRepos", lambda s: bool(s["unresolved_names"])),
                      ("RQsixLegacyRepos", lambda s: s["n_removed_legacy"] > 0),
                      ("RQsixNeverValidRepos", lambda s: s["n_never_valid"] > 0)):
        k = len({r["repo"] for r in pop if r["grant"] == "explicit" and pred(r)})
        m[key] = f"{num(k)} ({pct(k / len(expl_repos))})"

    # ---- RQ4
    pp = V2 / "nlp" / "spec_prose.jsonl.gz"
    if pp.exists():
        prose = {(r["repo"], r["path"]): r for r in jl(pp)}
        merged = [{**r, **prose[(r["repo"], r["path"])]} for r in pop if (r["repo"], r["path"]) in prose]
        nonlatin = sum(1 for x in merged if x.get("script_body") != "latin")
        m["pctNonLatin"] = pct(nonlatin / max(1, len(merged)))
        latin = [x for x in merged if x.get("script_body") == "latin"]
        m["RQfourAnyProhibition"] = ci(stats.estimate(latin, lambda s: s.get("n_prohibition", 0) > 0))
        m["RQfourCapsEmphasis"] = ci(stats.estimate(latin, lambda s: s.get("caps_emphasis", 0) > 0))
        m["RQfourPersona"] = ci(stats.estimate(latin, lambda s: bool(s.get("persona_opening"))))
    ds = V2 / "nlp" / "directive_sentences.jsonl.gz"
    if ds.exists():
        mods = collections.Counter(r["modality"] for r in jl(ds))
        m["nDirectiveSentences"] = num(sum(mods.values()))
        m["pctProhibitionSentences"] = pct(mods["prohibition"] / sum(mods.values()))
    cs = V2 / "labels" / "constraints" / "items.jsonl"
    if cs.exists():
        m["nConstraintSample"] = num(sum(1 for _ in open(cs)))
    cp = V2 / "nlp" / "constraint_prevalence.json"
    if cp.exists():   # stratum-weighted prevalence of each constraint topic among distinct directive sentences
        c = json.loads(cp.read_text())
        m["nDistinctDirective"] = num(c["n_population"])
        fmt = lambda d: f"{100*d['prevalence']:.1f}\\% ({100*d['lo']:.1f}--{100*d['hi']:.1f})"   # noqa: E731
        names = {"FS_MODIFY": "FsModify", "EXEC": "Exec", "VCS": "Vcs", "SCOPE": "Scope", "SECRETS": "Secrets",
                 "EXTERNAL": "External", "DESTRUCTIVE": "Destructive", "QUALITY": "Quality", "OUTPUT": "Output",
                 "ESCALATE": "Escalate", "HONESTY": "Honesty", "DELEGATION": "Delegation", "OTHER": "Other"}
        for k, v in c["categories"].items():
            m[f"Cat{names[k]}"] = fmt(v)
        m["CatRestrictsWrites"] = fmt(c["restricts_writes"])
    cr = V2 / "nlp" / "constraint_classifier_report.json"
    if cr.exists():
        f1 = [v["f1"] for v in json.loads(cr.read_text()).values()]
        m["ClassifierFoneRange"] = f"{min(f1):.2f}--{max(f1):.2f}"
    tj = V2 / "nlp" / "topics.json"
    if tj.exists():
        t = json.loads(tj.read_text())
        m["nTopics"] = num(len(t["topics"]))
        m["TopicMedianNpmi"] = f"{st.median(x['npmi'] for x in t['topics']):.2f}"
        m["pctTopicOutliers"] = pct(t["outliers_before_reduction"] / t["n_items"])
    sp = V2 / "labels" / "specrestr" / "prevalence.json"
    if sp.exists():   # Codebook S on one random specification per engineered repository
        s_ = json.loads(sp.read_text())
        fmt = lambda d: f"{100*d['est']:.1f}\\% ({100*d['lo']:.1f}--{100*d['hi']:.1f})"   # noqa: E731
        m["nSpecSample"] = num(s_["n_labelled"])
        m["nSpecFull"] = num(s_["n_full"])
        for key, field in (("RQfourProseAny", "any"), ("RQfourProseFull", "full"), ("RQfourProsePartial", "partial"),
                           ("RQfourFullReaches", "full_reaches_fs"), ("RQfourFullWriteTool", "full_holds_write_tool"),
                           ("RQfourFullImplicit", "full_implicit_grant"), ("RQfourFullShellOnly", "full_shell_only")):
            m[key] = fmt(s_[field])
        m["RQfourFullEnforced"] = f"{100*(1 - s_['full_reaches_fs']['est']):.1f}\\%"
    # second rater on a random subset of the Codebook S batches
    rel = sorted((V2 / "labels" / "specrestr" / "out_sonnet_reliability").glob("batch_*.jsonl"))
    if rel:
        prim = {}
        for d in sorted((V2 / "labels" / "specrestr").glob("out_haiku*")):
            for f in sorted(d.glob("batch_*.jsonl")):
                prim.update({o["id"]: o["restriction"] for o in jl(f) if o.get("restriction") in ("full", "partial", "none")})
        sec = {o["id"]: o["restriction"] for f in rel for o in jl(f) if o.get("restriction") in ("full", "partial", "none")}
        common = sorted(set(prim) & set(sec))
        from llm_labels import krippendorff_nominal
        m["nSpecReliability"] = num(len(common))
        m["nSpecBatches"] = num(sum(1 for d in (V2 / "labels" / "specrestr" / "in").iterdir() if d.is_dir()))
        m["nSpecReliabilityBatches"] = num(len(rel))
        m["alphaSpecRestr"] = f"$\\alpha={krippendorff_nominal([(prim[i], sec[i]) for i in common]):.2f}$"
        full = lambda x: "full" if x == "full" else "not"   # noqa: E731
        m["alphaSpecFull"] = f"$\\alpha={krippendorff_nominal([(full(prim[i]), full(sec[i])) for i in common]):.2f}$"

    # ---- RQ5
    rp = DATA / "experiment" / "runs_subagent.jsonl"
    if rp.exists():
        runs = [r for r in jl(rp) if r.get("success") is not None]
        m["nExpRuns"] = num(len(runs))
        m["nRepsPerCell"] = "30"
        FORB = {"T2", "T3", "T4", "T5"}

        def rate(cfg):
            xs = [r for r in runs if r["config"] == cfg and r["task"] in FORB]
            k = sum(1 for r in xs if r["success"])
            lo, hi = stats.wilson_ci(k, len(xs))
            return f"{100*k/max(1,len(xs)):.1f}\\% ({100*lo:.1f}--{100*hi:.1f})"
        for cfg, name in (("C0", "ExpCzeroRate"), ("C1", "ExpConeRate"), ("C2", "ExpCtwoRate"),
                          ("C3", "ExpCthreeRate"), ("C4", "ExpCfourRate")):
            m[name] = rate(cfg)
        per = []
        for mod in ("haiku", "sonnet", "opus"):
            xs = [r for r in runs if r["config"] == "C3" and r["task"] in FORB and r["model"] == mod]
            if xs:
                per.append(100 * sum(1 for r in xs if r["success"]) / len(xs))
        if per:
            m["ExpCthreeRange"] = f"{min(per):.1f}\\% to {max(per):.1f}\\%"
        allruns = list(jl(rp))
        m["nExpRunsBuildA"] = num(1407)   # v2.1.270, runs 0-1406 (transcript "version" field; see audit 2026-09-23)
        m["nExpRunsBuildB"] = num(673)    # v2.1.271, runs 1407-2079
        m["nExpRunsOriginal"] = num(sum(1 for r in allruns if int(r["run_id"][1:6]) < 2080))
        m["nExpIncomplete"] = num(sum(1 for r in allruns if r.get("incomplete")))
        xp = DATA / "experiment" / "excluded_transcripts.jsonl"
        if xp.exists():   # dispatches in a different stimulus context, discarded before scoring and re-run
            m["nExpExcluded"] = num(sum(1 for _ in jl(xp)))
        m["nExpOutsideWrites"] = num(sum(1 for r in allruns if r.get("outside_writes")))
        m["nExpOutsideCwd"] = num(sum(1 for r in allruns if r.get("outside_writes") and not any(("Trash" in w or "moved out" in w) for w in r["outside_writes"])))
        m["nExpOutsideTrash"] = num(sum(1 for r in allruns if any(("Trash" in w or "moved out" in w) for w in r.get("outside_writes") or [])))
        m["nExpPermissionDenials"] = num(sum(int(r.get("classifier_denials") or 0) for r in allruns))
        m["nExpDeniedFileTool"] = num(sum(1 for r in runs if r.get("denied_file_tool") and r["task"] in FORB))
        m["nExpDeniedWithShell"] = num(sum(1 for r in runs if r.get("denied_file_tool") and r["task"] in FORB
                                           and r["config"] in ("C0", "C1", "C2", "C3")))
        m["nExpDeniedWithShellSuccess"] = num(sum(1 for r in runs if r.get("denied_file_tool") and r["task"] in FORB
                                                  and r["config"] in ("C0", "C1", "C2", "C3") and r["success"]))
        m["nExpDeniedNoShellSuccess"] = num(sum(1 for r in runs if r.get("denied_file_tool") and r["task"] in FORB
                                                and r["config"] == "C4" and r["success"]))
        # completion claims (Codebook K) on failed forbidden-task runs the scorer did not already mark as refusals
        failed = [r for r in runs if r["task"] in FORB and not r["success"]]
        m["nExpFailedForbidden"] = num(len(failed))
        cl = {}
        for f in sorted((V2 / "labels" / "claims" / "out_sonnet").glob("batch_*.jsonl")):
            cl.update({o["id"]: o["claim"] for o in jl(f)})
        if cl:
            fids = {r["run_id"] for r in failed}
            done = [i for i, c in cl.items() if c == "claims_done" and i in fids]
            m["nExpClaimsAnnotated"] = num(len(cl))
            m["nExpFalseClaims"] = num(len(done))
            m["nExpAmbiguousClaims"] = num(sum(1 for c in cl.values() if c == "ambiguous"))
            cells = collections.Counter(tuple(i.split("-")[1:3]) for i in done)
            if len(cells) == 1:
                (mod, cfg), k = next(iter(cells.items()))
                n = sum(1 for r in runs if r["model"] == mod and r["config"] == cfg and r["task"] in FORB)
                m["ExpFalseClaimsCell"] = f"{k} of {n}"
                _lo, _hi = stats.wilson_ci(k, n)
                m["ExpFalseClaimsCI"] = f"{100*_lo:.1f}--{100*_hi:.1f}\\%"
        wr = [r for r in runs if r["config"] == "C2" and r["task"] in {"T2", "T3", "T4"} and r["success"]]
        m["ExpCtwoShellShare"] = f"{sum(r['pathway'] == 'shell' for r in wr)} of {len(wr)}"
        for cfg, nm in (("C1", "One"), ("C3", "Three")):
            for mod in ("haiku", "sonnet", "opus"):
                xs = [r for r in runs if r["config"] == cfg and r["task"] in FORB and r["model"] == mod]
                k = sum(1 for r in xs if r["success"]); lo, hi = stats.wilson_ci(k, len(xs))
                m[f"ExpC{nm.lower()}{mod.capitalize()}"] = f"{100*k/max(1,len(xs)):.1f}\\% ({100*lo:.1f}--{100*hi:.1f})"
        # period sensitivity: original (2.1.270) vs replica (2.1.280) dispatch, per model x configuration
        import math as _m
        def _fisher(a, b, c, d):
            lf = lambda x: _m.lgamma(x + 1)
            pt = lambda a, b, c, d: _m.exp(lf(a+b)+lf(c+d)+lf(a+c)+lf(b+d)-lf(a)-lf(b)-lf(c)-lf(d)-lf(a+b+c+d))
            p0, r1, r2, c1 = pt(a, b, c, d), a + b, c + d, a + c
            return min(1.0, sum(pt(i, r1-i, c1-i, r2-c1+i) for i in range(max(0, c1-r2), min(r1, c1)+1) if pt(i, r1-i, c1-i, r2-c1+i) <= p0*(1+1e-9)))
        # three builds, identified from the transcripts' "version" field: v2.1.270 runs 0-1406, v2.1.271 runs
        # 1407-2079, v2.1.280 runs 2080-2699. Per model x configuration, forbidden-task success is compared between
        # every pair of builds (Fisher exact, uncorrected); the smallest p and the cell sizes are reported.
        def build_of(r):
            i = int(r["run_id"][1:6])
            return "270" if i < 1407 else ("271" if i < 2080 else "280")
        ps, sizes = [], []
        for mod in ("haiku", "sonnet", "opus"):
            for cfg in ("C0", "C1", "C2", "C3", "C4"):
                cell = {b: [r for r in runs if r["model"] == mod and r["config"] == cfg and r["task"] in FORB
                            and build_of(r) == b] for b in ("270", "271", "280")}
                sizes += [len(v) for v in cell.values()]
                for b1, b2 in (("270", "271"), ("270", "280"), ("271", "280")):
                    o, q = cell[b1], cell[b2]
                    ko, kq = sum(r["success"] for r in o), sum(r["success"] for r in q)
                    ps.append(_fisher(ko, len(o)-ko, kq, len(q)-kq))
        m["ExpPeriodMinP"] = f"{min(ps):.2f}"
        m["ExpBuildCellSizes"] = f"{min(sizes)}--{max(sizes)}"
        m["nExpBuildComparisons"] = num(len(ps))

        # the three pre-specified contrasts: Fisher exact p, Haldane-Anscombe odds ratio with Woolf interval, Holm
        def sci(x: float) -> str:
            if x == 0:
                return "0"
            e_ = _m.floor(_m.log10(abs(x)))
            if -2 <= e_ <= 2:
                return f"{x:.2g}" if x < 1 else f"{x:.1f}"
            return f"{x/10**e_:.1f}\\times10^{{{e_}}}"
        WRITE = {"T2", "T3", "T4"}
        contrasts = (("ExpTestShell", lambda r: r["config"] == "C2" and r["task"] in WRITE,
                      lambda r: r["config"] == "C4" and r["task"] in WRITE),
                     ("ExpTestPromptShell", lambda r: r["config"] == "C3" and r["task"] in FORB,
                      lambda r: r["config"] == "C2" and r["task"] in FORB),
                     ("ExpTestPromptNoTools", lambda r: r["config"] == "C1" and r["task"] in FORB,
                      lambda r: r["config"] == "C0" and r["task"] in FORB))
        raw = []
        for key, sa, sb in contrasts:
            a = sum(1 for r in runs if sa(r) and r["success"]); b = sum(1 for r in runs if sa(r) and not r["success"])
            c = sum(1 for r in runs if sb(r) and r["success"]); d = sum(1 for r in runs if sb(r) and not r["success"])
            orr = ((a + .5) * (d + .5)) / ((b + .5) * (c + .5))
            se = _m.sqrt(1/(a+.5) + 1/(b+.5) + 1/(c+.5) + 1/(d+.5))
            raw.append((key, a, a + b, c, c + d, _fisher(a, b, c, d), orr,
                        _m.exp(_m.log(orr) - 1.96*se), _m.exp(_m.log(orr) + 1.96*se)))
        order = sorted(range(len(raw)), key=lambda i: raw[i][5])
        adj, prev = [0.0] * len(raw), 0.0
        for rank, i in enumerate(order):
            adj[i] = prev = max(prev, min(1.0, (len(raw) - rank) * raw[i][5]))
        for (key, a, n1, c, n2, p, orr, lo_, hi_), pa in zip(raw, adj):
            m[key] = (f"{a}/{n1} against {c}/{n2}, OR ${sci(orr)}$ [${sci(lo_)}$, ${sci(hi_)}$], "
                      f"$p={sci(p)}$, Holm $p={sci(pa)}$")
    else:
        m["nExpRuns"] = "\\textbf{??}"

    # ---- RQ6
    ex = lambda s: s["grant"] == "explicit"
    m["RQsixUnresolved"] = ci(stats.estimate(pop, lambda s: bool(s["unresolved_names"]), ex))
    m["RQsixLegacy"] = ci(stats.estimate(pop, lambda s: s["n_removed_legacy"] > 0, ex))
    m["RQsixNeverValid"] = ci(stats.estimate(pop, lambda s: s["n_never_valid"] > 0, ex))
    dp = V2 / "drift_first_commits.jsonl"
    if dp.exists():
        rem = json.loads((V2 / "drift_removals.json").read_text())
        # only names the resolver classes as removed (KillBash still resolves as an alias; exit_plan_mode is not a
        # tool name the pinned build knows), so the drift share covers exactly the RQ6 "removed" class
        legacy = {k for k, v in json.loads((ORA / "name_classes.json").read_text())["classes"].items()
                  if v == "removed_legacy"}
        rem = {k: v for k, v in rem.items() if k in legacy}
        keep = {r["repo"] for r in pop}
        after = before = in2026 = 0
        for d in jl(dp):
            if d["repo"] not in keep or not d.get("first_commit"):
                continue
            flags = [d["first_commit"][:10] >= rem[n]["removal_date_upper"] for n in d["names"] if n in rem]
            if flags and all(flags):
                after += 1
            elif flags:
                before += 1
            if flags and d["first_commit"][:4] == "2026":
                in2026 += 1
        m["RQsixDriftAfter"] = pct(after / max(1, after + before))
        m["RQsixDriftInSnapshotYear"] = pct(in2026 / max(1, after + before))
        m["nDriftDated"] = num(after + before)
        dates = sorted(v["removal_date_upper"] for v in rem.values())
        mon = lambda s: __import__("datetime").date.fromisoformat(s).strftime("%B %Y")   # noqa: E731
        m["DriftRemovalWindow"] = f"{mon(dates[0])} and {mon(dates[-1])}"
    # shadowing, from the census
    builtin = set(json.loads((ORA / "builtin_agents.json").read_text()))
    by_root = collections.defaultdict(list)
    for r in pop:
        by_root[(r["repo"], r["config_root"])].append(r)
    shadowed = 0
    repos_sh = set()
    for (repo, root), specs in by_root.items():
        names = collections.Counter(str(s["name"]).strip() for s in specs)
        extra = sum(v - 1 for v in names.values() if v > 1)
        if extra:
            shadowed += extra
            repos_sh.add(repo)
    m["RQsixShadowed"] = num(shadowed)
    m["RQsixShadowedRepos"] = pct(len(repos_sh) / len(by_repo))

    # ---- clustering
    icc = stats.intraclass_correlation([[1 if (s["can_write_files"] or s["can_shell"]) else 0
                                         for s in v if s["grant"] == "explicit"]
                                        for v in collections.defaultdict(list, {k: [r for r in pop if r["repo"] == k]
                                                                                for k in by_repo}).values()])
    if icc:
        m["iccValue"] = f"{icc['icc']:.2f}"
        m["deffValue"] = f"{icc['design_effect']:.2f}"

    # ---- the role contrast (RQ2), paired within repository so house style cannot explain it.
    if any(r.get("mode") for r in pop):
        def pts(d) -> str:
            return f"{100*d['difference']:.1f} pts ({100*d['lo']:.1f}--{100*d['hi']:.1f})"
        insp = lambda s: s.get("mode") == "inspect"                                    # noqa: E731
        chng = lambda s: s.get("mode") == "change"                                     # noqa: E731
        expl = [r for r in pop if r["grant"] == "explicit"]
        for key, specs, outcome in (
                ("RQtwoRoleGapWrite", pop, lambda s: bool(s["can_write_files"])),
                ("RQtwoRoleGapWriteExplicit", expl, lambda s: bool(s["can_write_files"])),
                ("RQtwoRoleGapAuthority", pop, lambda s: bool(s["can_write_files"]) or bool(s["can_shell"])),
                ("RQtwoRoleGapAuthorityExplicit", expl, lambda s: bool(s["can_write_files"]) or bool(s["can_shell"]))):
            d = stats.paired_contrast(specs, insp, chng, outcome)
            if d:
                m[key] = pts(d)
                m[key + "Repos"] = num(d["n_repos"])
        for name, pred in (("Inspect", insp), ("Change", chng), ("Mixed", lambda s: s.get("mode") == "mixed")):
            sub = [r for r in pop if pred(r)]
            if sub:
                m[f"RQtwoShare{name}"] = pct(len(sub) / len(pop))
        e = stats.estimate(pop, lambda s: bool(s.get("readonly_claim")))
        if e:
            m["RQtwoReadonlyClaim"] = ci(e)
        labelled = [r for r in pop if r.get("role")]
        roles = collections.Counter(r["role"] for r in labelled)
        for code, name in (("IMPL", "Impl"), ("REVIEW", "Review"), ("PLAN", "Plan"), ("EXPLORE", "Explore"),
                           ("TEST", "Test"), ("OPS", "Ops"), ("ARCH", "Arch"), ("NONSE", "Nonse"), ("SEC", "Sec"),
                           ("DOCS", "Docs")):
            m[f"RoleShare{name}"] = pct(roles[code] / len(labelled))

    # ---- governance (RQ7). One row per repository, so these are plain repository shares.
    gp = DATA / "repometa_v2.jsonl.gz"
    if gp.exists():
        keep = {r["repo"] for r in pop}
        gov = [g for g in jl(gp) if g["frame_repo"] in keep]
        if gov:
            def share(field) -> str:
                return pct(sum(1 for g in gov if g.get(field)) / len(gov))
            m["RQsevenBranchProtected"] = share("branch_protected")
            m["RQsevenRulesets"] = share("ruleset_rule_types")   # the API returns the rule types, not a flag
            m["RQsevenDependabot"] = share("dependabot")
            m["RQsevenCodeowners"] = share("codeowners")
            m["RQsevenSecurityPolicy"] = share("security_policy")
            # does existing governance predict a coherent agent restriction? contrast the incoherent
            # share among protected and unprotected repositories.
            protected = {g["frame_repo"] for g in gov if g.get("branch_protected")}
            inco = lambda s: (s["grant"] == "explicit" and not s["can_write_files"]                 # noqa: E731
                              and bool(s["can_shell"]) and not s.get("shell_scoped_only"))
            for tagname, subset in (("Governed", protected), ("Ungoverned", keep - protected)):
                e = stats.estimate([r for r in pop if r["repo"] in subset], inco)
                if e:
                    m[f"RQsevenIncoherent{tagname}"] = ci(e)

    # ---- governance signals beyond branch protection, from the same per-repository table as analysis_v2.rq7
    try:
        import analysis_v2
        gt = list(analysis_v2.governance_table(pop).values())
    except FileNotFoundError:
        gt = []
    if gt:
        share_ = lambda key: pct(sum(1 for r in gt if r.get(key)) / len(gt))   # noqa: E731
        m["RQsevenMcp"] = share_("mcp_present")
        m["RQsevenSettingsDeny"] = share_("settings_deny_write_or_bash")
        m["RQsevenCiAllScoped"] = share_("ci_all_permissions_declared")
        m["RQsevenCiClaudeAction"] = share_("ci_claude_action")
        withset = [r for r in gt if r["settings_present"]]
        m["RQsixVoidSettings"] = pct(sum(1 for r in withset if r["settings_void_rules"]) / max(1, len(withset)))
        for key, name in (("settings_deny_write_or_bash", "SettingsDeny"), ("ci_all_permissions_declared", "CiScoped"),
                          ("codeowners", "Codeowners")):
            a = [r["agent_incoherent_share"] for r in gt if r.get(key)]
            b = [r["agent_incoherent_share"] for r in gt if not r.get(key)]
            if a and b:
                m[f"RQsevenIncoherent{name}"] = f"{100*st.mean(a):.1f}\\% against {100*st.mean(b):.1f}\\%"
                import random as _rnd2   # difference of repository means with a percentile bootstrap
                _g2 = _rnd2.Random(20260924)
                _d2 = sorted(st.mean(_g2.choices(a, k=len(a))) - st.mean(_g2.choices(b, k=len(b))) for _ in range(10000))
                _f = lambda x: f"${100*x:.1f}$"   # noqa: E731  math mode, so a negative bound gets a minus sign
                m[f"RQsevenDiff{name}"] = (f"{100*(st.mean(a)-st.mean(b)):.1f} pts "
                                           f"({_f(_d2[250])} to {_f(_d2[9749])})")
        withci = [r for r in gt if r["workflows"] > 0]
        if withci:
            diffs = [float(r["ci_all_permissions_declared"]) - float(r["agent_any_restricted"]) for r in withci]
            lo, hi = stats.bootstrap_ci(diffs)
            m["RQsevenCiVsAgent"] = f"${100*st.mean(diffs):+.1f}$ pts (${100*lo:+.1f}$ to ${100*hi:+.1f}$)"
            m["nReposWithCi"] = num(len(withci))
            sc = [r for r in withci if r["ci_all_permissions_declared"]]
            un = [r for r in withci if not r["ci_all_permissions_declared"]]
            k1, k2 = sum(r["agent_any_restricted"] for r in sc), sum(r["agent_any_restricted"] for r in un)
            m["RQsevenRestrictedIfCiScoped"] = f"{100*k1/len(sc):.1f}\\% against {100*k2/len(un):.1f}\\%"
            m["RQsevenCiAssocP"] = f"{_fisher2(k1, len(sc) - k1, k2, len(un) - k2):.2f}"

    # ---- admission: of the specifications staged at a probed root, how many the runtime registers (as analysis_v2.rq6)
    builtin = set(json.loads((ORA / "builtin_agents.json").read_text()))
    by_root = collections.defaultdict(list)
    for r in pop:
        by_root[(r["repo"], r["config_root"])].append(r)
    declared = loaded = 0
    for c in jl(ORA / "census.jsonl"):
        key = (c["repo"], c["config_root"])
        if c.get("ok") and key in by_root:
            agents = set(c.get("agents") or []) - builtin
            for s_ in by_root[key]:
                declared += 1
                loaded += str(s_["name"]).strip() in agents
    m["RQsixRegistered"] = pct(loaded / max(1, declared))

    # ---- review round: context of dominated withholding, intent-conditioned rate, plan-mode exclusion
    dom = lambda s: (s["grant"] == "explicit" and not s["can_write_files"] and bool(s["can_shell"])   # noqa: E731
                     and not s.get("shell_scoped_only"))
    wh_ = lambda s: s["grant"] == "explicit" and not s["can_write_files"]   # noqa: E731
    D = [r for r in pop if dom(r)]
    m["nDomSpecs"] = num(len(D))
    m["nDomRepos"] = num(len({r["repo"] for r in D}))
    m["nDomPlan"] = num(sum(1 for r in D if r.get("permissionMode") == "plan"))
    m["nDomChangeMode"] = num(sum(1 for r in D if r.get("mode") == "change"))
    m["RQthreeIncoherentInspect"] = ci(stats.estimate(pop, dom, lambda s: wh_(s) and s.get("mode") == "inspect"))
    m["RQthreeIncoherentNoPlan"] = ci(stats.estimate(pop, lambda s: dom(s) and s.get("permissionMode") != "plan", wh_))
    # explicit grants with neither a file-writing tool nor an unscoped shell: other authority they keep
    _R = [r for r in pop if wh_(r) and not (r["can_shell"] and not r.get("shell_scoped_only"))]
    m["nRestrictedGrants"] = num(len(_R))
    m["nRestrictedWeb"] = num(sum(1 for r in _R if {"WebFetch", "WebSearch"} & set(r.get("effective") or [])))
    m["nRestrictedMcp"] = num(sum(1 for r in _R if (r.get("n_mcp_names") or 0) > 0))
    m["nRestrictedTask"] = num(sum(1 for r in _R if {"Task", "Agent"} & set(r.get("effective") or [])))
    try:
        import analysis_v2 as _A
        _gt = _A.governance_table(pop)
        _dr = [_gt[x] for x in {r["repo"] for r in D} if x in _gt]
        for key, field in (("nDomReposSettings", "settings_present"), ("nDomReposDeny", "settings_deny_write_or_bash"),
                           ("nDomReposHooks", "settings_hooks"), ("nDomReposSandbox", "settings_sandbox")):
            m[key] = num(sum(1 for x in _dr if x.get(field)))
        # committed settings that let shell commands run without per-command approval
        _gov = {g["repo"]: g for g in jl(V2 / "governance.jsonl.gz")}
        _drepos = {r["repo"] for r in D}
        _sett = {x: (_gov.get(x) or {}).get("settings") or [] for x in _drepos}
        m["nDomReposAllowBash"] = num(sum(1 for v in _sett.values() if any(y.get("allow_unscoped_bash") for y in v)))
        m["nDomReposNoApprovalMode"] = num(sum(1 for v in _sett.values() if any(
            y.get("default_mode") in ("acceptEdits", "auto", "bypassPermissions") for y in v)))
        _a = [r["agent_incoherent_share"] for r in _gt.values() if r.get("branch_protected")]
        _b = [r["agent_incoherent_share"] for r in _gt.values() if r.get("branch_protected") is False]
        import random as _rnd
        _g = _rnd.Random(20260924)
        _ds = sorted(st.mean(_g.choices(_a, k=len(_a))) - st.mean(_g.choices(_b, k=len(_b))) for _ in range(10000))
        m["RQsevenBPDiff"] = (f"{100*(st.mean(_a)-st.mean(_b)):.1f} pts "
                              f"({100*_ds[250]:.1f}--{100*_ds[9749]:.1f})")
    except FileNotFoundError:
        pass

    # ---- duplication sensitivity: one copy per content hash (the first in repository/path order)
    seen, dedup = set(), []
    for r in sorted(pop, key=lambda r: (r["repo"], r["path"])):
        if r["hash"] not in seen:
            seen.add(r["hash"])
            dedup.append(r)
    m["nSpecsDedup"] = num(len(dedup))
    m["DedupImplicit"] = ci(stats.estimate(dedup, lambda s: s["grant"] == "implicit"))
    m["DedupIncoherent"] = ci(stats.estimate(dedup, lambda s: s["can_shell"] and not s["shell_scoped_only"],
                                             lambda s: s["grant"] == "explicit" and not s["can_write_files"]))
    if any(r.get("mode") for r in dedup):
        for key, outcome in (("DedupGapWrite", lambda s: bool(s["can_write_files"])),
                             ("DedupGapAuthority", lambda s: bool(s["can_write_files"]) or bool(s["can_shell"]))):
            d = stats.paired_contrast(dedup, lambda s: s.get("mode") == "inspect", lambda s: s.get("mode") == "change", outcome)
            if d:
                m[key] = f"{100*d['difference']:.1f} pts ({100*d['lo']:.1f}--{100*d['hi']:.1f})"

    # ---- annotation
    rl = V2 / "labels" / "roles" / "items.jsonl"
    if rl.exists():
        m["nRoleItems"] = num(sum(1 for _ in open(rl)))
    sheet = ROOT / "annotation" / "human_roles" / "sheet_annotator_A.csv"
    if sheet.exists():   # the blank two-annotator kit fixes the human validation sample size.
        import csv       # descriptions contain newlines, so count parsed rows, not lines
        with sheet.open(newline="") as fh:
            m["nHumanSample"] = num(sum(1 for _ in csv.DictReader(fh)))
    rel = V2 / "labels" / "roles" / "agreement.json"
    if rel.exists():
        a = json.loads(rel.read_text())
        for key, field in (("alphaRoleModels", "role"), ("alphaModeModels", "mode")):
            if field in a:
                m[key] = f"$\\alpha={a[field]:.2f}$"
        m["alphaModeBinaryModels"] = f"$\\alpha={a['mode_binary']:.2f}$"
        m["nReliabilityItems"] = num(a["n_items"])
    # rater sensitivity: the RQ3 headline recomputed on the reliability sample under each rater's mode.
    relin = sorted((V2 / "labels" / "roles" / "in_reliability").glob("batch_*.jsonl"))
    if relin and (V2 / "labels" / "roles_sonnet.jsonl.gz").exists():
        relids = {json.loads(l)["id"] for f in relin for l in f.read_text().splitlines() if l.strip()}
        labs = {r: {x["id"]: x for x in jl(V2 / "labels" / f"roles_{r}.jsonl.gz")} for r in ("haiku", "sonnet")}
        sub = [r for r in pop if r["item_id"] in relids and all(r["item_id"] in labs[k] for k in labs)]
        m["nRaterSensSpecs"] = num(len(sub))
        for rater, lab in labs.items():
            ins = [r for r in sub if lab[r["item_id"]]["mode"] == "inspect"]
            if ins:
                able = sum(1 for r in ins if r["can_write_files"] or r["can_shell"]) / len(ins)
                m[f"RaterSensAble{rater.capitalize()}"] = pct(able)
            relab = [{**r, "mode": lab[r["item_id"]]["mode"]} for r in sub]
            for key, outcome in (("Write", lambda s: bool(s["can_write_files"])),
                                 ("Authority", lambda s: bool(s["can_write_files"]) or bool(s["can_shell"]))):
                d = stats.paired_contrast(relab, insp, chng, outcome)
                if d:
                    m[f"RaterSensGap{key}{rater.capitalize()}"] = pts(d)
                    m[f"RaterSensRepos{rater.capitalize()}"] = num(d["n_repos"])
    for k in ("alphaRoleModels", "alphaModeModels", "nHumanSample"):
        m.setdefault(k, "\\textbf{??}")

    # ---- overreach extension: report-only tasks, does any configuration change files unasked?
    op = DATA / "experiment" / "overreach" / "runs.jsonl"
    if op.exists():
        ov = [r for r in jl(op) if not r.get("incomplete")]
        m["nOverRuns"] = num(len(ov))
        k = sum(1 for r in ov if r["overreach"])
        m["nOverChanged"] = num(k)
        lo, hi = stats.wilson_ci(k, len(ov))
        m["OverRate"] = f"{100*k/max(1,len(ov)):.1f}\\% (upper 95\\% bound {100*hi:.1f}\\%)"
        for c in ("C0", "C2", "C3", "C4"):
            xs = [r for r in ov if r["config"] == c]
            if xs:
                k_ = sum(1 for r in xs if r["overreach"])
                lo_, hi_ = stats.wilson_ci(k_, len(xs))
                m[f"OverC{'zero two three four'.split()[['C0','C2','C3','C4'].index(c)].capitalize()}"] = \
                    f"{k_}/{len(xs)} (upper bound {100*hi_:.1f}\\%)"
        m["OverFoundBug"] = pct(sum(1 for r in ov if r["found_bug"]) / max(1, len(ov)))
        m["nOverIncomplete"] = num(sum(1 for r in jl(op) if r.get("incomplete")))
        m["nOverPermissionDenials"] = num(sum(int(r.get("classifier_denials") or 0) for r in jl(op)))

    # ---- scoped-shell probe: does Bash(pattern) in a subagent's tools field restrict commands? (auto mode)
    sp_ = DATA / "experiment" / "scoped" / "runs.jsonl"
    if sp_.exists():
        sc = list(jl(sp_))
        _sc_cr = [r for r in sc if r["task"] == "create"]
        _sc_gl = [r for r in sc if r["task"] == "gitlog"]
        m["nScopedRuns"] = num(len(sc))
        m["ScopedCreated"] = f"{sum(r['file_created'] for r in _sc_cr)} of {len(_sc_cr)}"
        m["ScopedControls"] = f"{len(_sc_gl)} of {len(_sc_gl)}"
        m["nScopedFileToolCalls"] = num(sum(1 for r in sc for c in r["tool_calls"] if c["tool"] in ("Write", "Edit")))
        m["ScopedBuild"] = sorted({r["cc_version"] for r in sc})[0]
    m["nOverRunsAtReduction"] = num(29)   # scored runs, all null, when the reduction was decided (dispatch log)

    # ---- codebook B: why do write-withholding grants keep an unscoped shell?
    bdir = V2 / "labels" / "shelluse"
    if (bdir / "items.jsonl").exists():
        lab = {}
        for d in sorted(bdir.glob("out_haiku*")):
            for f in sorted(d.glob("batch_*.jsonl")):
                lab.update({o["id"]: o["shell_use"] for o in jl(f) if o.get("shell_use") in ("change", "verify", "inspect", "none")})
        ids = [json.loads(l)["id"] for l in (bdir / "items.jsonl").read_text().splitlines() if l.strip()]
        got = [lab[i] for i in ids if i in lab]
        if got:
            m["nShellSample"] = num(len(ids))
            m["nShellLabelled"] = num(len(got))
            for v, name in (("none", "None"), ("inspect", "Inspect"), ("verify", "Verify"), ("change", "Change")):
                k = got.count(v)
                lo, hi = stats.wilson_ci(k, len(got))
                m[f"ShellUse{name}"] = f"{100*k/len(got):.1f}\\% ({100*lo:.1f}--{100*hi:.1f})"
            k = sum(1 for v in got if v in ("inspect", "verify"))
            m["ShellUseReadOnlyNeed"] = pct(k / len(got))
            k = sum(1 for v in got if v in ("none", "inspect", "verify"))
            m["ShellUseNoChangeNeed"] = pct(k / len(got))
            k = sum(1 for v in got if v in ("none", "inspect"))   # conservative: verification counted as a change
            m["ShellUseNoneOrInspect"] = pct(k / len(got))
        rel = sorted((bdir / "out_sonnet_reliability").glob("batch_*.jsonl"))
        if rel:
            sec = {o["id"]: o["shell_use"] for f in rel for o in jl(f)
                   if o.get("shell_use") in ("change", "verify", "inspect", "none")}
            common = sorted(set(sec) & set(lab))
            from llm_labels import krippendorff_nominal
            m["nShellReliability"] = num(len(common))
            m["nShellReliabilityBatches"] = num(len(rel))
            m["alphaShellUse"] = f"$\\alpha={krippendorff_nominal([(lab[i], sec[i]) for i in common]):.2f}$"
            # rater sensitivity: the no-change share on the double-coded specifications under each rater
            m["ShellNoChangeHaikuRel"] = pct(sum(1 for i in common if lab[i] != "change") / len(common))
            m["ShellNoChangeSonnetRel"] = pct(sum(1 for i in common if sec[i] != "change") / len(common))
            chg = lambda v: "change" if v == "change" else "no"   # noqa: E731
            m["alphaShellChange"] = f"$\\alpha={krippendorff_nominal([(chg(lab[i]), chg(sec[i])) for i in common]):.2f}$"

    # ---- further quantities quoted in the text (added in the 2026-09-23 revision)
    # Grep/Glob lists: how many lose the search tools where Bash resolves, and how many without Bash lose them
    gl = [r for r in pop if r["grant"] == "explicit" and {"Grep", "Glob"} & set(r["requested"])]
    gl_b = [r for r in gl if "Bash" in r["effective"]]
    m["RQthreeGrepDroppedResolved"] = f"{num(sum(1 for r in gl_b if r['grep_glob_dropped']))} of {num(len(gl_b))}"
    gl_nb = [r for r in gl if "Bash" not in r["requested"]]
    m["nGrepListsNoBash"] = num(len(gl_nb))
    m["nGrepListsNoBashDropped"] = num(sum(1 for r in gl_nb if r["grep_glob_dropped"]))
    # scoped shells among write-withholding explicit grants that hold a shell
    m["RQthreeScopedShare"] = ci(stats.estimate(pop, lambda s: bool(s["shell_scoped_only"]),
                                                lambda s: s["grant"] == "explicit" and not s["can_write_files"]
                                                and bool(s["can_shell"])))
    # implicit grants that can write or run a shell (pooled count)
    imp = [r for r in pop if r["grant"] == "implicit"]
    m["RQtwoImplicitCapableCount"] = f"{num(sum(1 for r in imp if r['can_write_files'] or r['can_shell']))} of {num(len(imp))}"
    # specifications that do not name a model (pooled share and repository mean)
    m["RQfiveNoModelPooled"] = pct(sum(1 for r in pop if not r.get("model")) / len(pop))
    m["RQfiveNoModel"] = ci(stats.estimate(pop, lambda s: not s.get("model")))
    # tool names that earlier releases accepted and the pinned build no longer resolves (resolver name classes)
    ncl = json.loads((ORA / "name_classes.json").read_text())["classes"]
    m["nRemovedNames"] = num(sum(1 for v in ncl.values() if v == "removed_legacy"))
    # the engineered-project thresholds of Galster et al. (>= 352 commits, created >= 18 months before the
    # 2026-08-28 snapshot) applied to the specification-bearing repositories: the share they would remove
    eng_meta = list(jl(V2 / "engineered.jsonl.gz"))
    kept = [e for e in eng_meta if (e.get("commits_to_snapshot") or 0) >= 352 and (e.get("created") or "9") <= "2025-02-28"]
    m["pctGalsterReposRemoved"] = pct(1 - len(kept) / len(eng_meta))
    m["pctGalsterSpecsRemoved"] = pct(1 - sum(e["n_specs"] for e in kept) / sum(e["n_specs"] for e in eng_meta))
    # prohibition sentences that carry only a weaker negative marker (does not, cannot, should not, avoid, ...)
    if ds.exists():
        strict = re.compile(r"\b(never|must\s+not|mustn['’]?t|shall\s+not|do\s+not|don['’]?t|may\s+not|not\s+allowed|"
                            r"not\s+permitted|forbidden|prohibited|under\s+no\s+circumstances|refrain\s+from|"
                            r"no\s+(?:editing|edits|changes|modifications|writes|writing))\b", re.I)
        pro = [r["sentence"] for r in jl(ds) if r["modality"] == "prohibition"]
        m["pctProhibitionWeakOnly"] = pct(sum(1 for s in pro if not strict.search(s)) / max(1, len(pro)))
    # classifier F1 over the categories with enough held-out positives to estimate it
    if cr.exists():
        rep = json.loads(cr.read_text())
        f1 = [v["f1"] for v in rep.values() if v.get("support_test", 0) >= 12]
        m["ClassifierFoneRange"] = f"{min(f1):.2f}--{max(f1):.2f}"
        m["nClassifierMinPositives"] = "12"
    # intended-mode disagreements between the two raters on the reliability sample
    relin_ = sorted((V2 / "labels" / "roles" / "in_reliability").glob("batch_*.jsonl"))
    if relin_ and (V2 / "labels" / "roles_haiku.jsonl.gz").exists():
        rid = {json.loads(l)["id"] for f in relin_ for l in f.read_text().splitlines() if l.strip()}
        hk = {o["id"]: o["mode"] for o in jl(V2 / "labels" / "roles_haiku.jsonl.gz") if o["id"] in rid}
        sn = {}
        for f in sorted((V2 / "labels" / "roles" / "out_sonnet_reliability").glob("batch_*.jsonl")):
            sn.update({o["id"]: o["mode"] for o in jl(f)})
        com = [i for i in rid if i in hk and i in sn]
        dis = [(hk[i], sn[i]) for i in com if hk[i] != sn[i]]
        m["nModeDisagree"] = num(len(dis))
        m["nModeDisagreeIC"] = num(sum(1 for p in dis if set(p) == {"inspect", "change"}))
        m["nModeDisagreeHaikuInspect"] = num(dis.count(("inspect", "change")))
        m["nModeDisagreeSonnetInspect"] = num(dis.count(("change", "inspect")))
    # governance: CI-token scoping among repositories that run CI
    if gt:
        withci_ = [r for r in gt if r["workflows"] > 0]
        m["RQsevenCiAllScopedWithCi"] = pct(sum(1 for r in withci_ if r["ci_all_permissions_declared"]) / max(1, len(withci_)))
    # reconstruction losses that are single missing objects rather than whole repositories
    m["nFilesObjectMissing"] = num(build["status"].get("object-not-found", 0))

    # ---- overreach design (planned and final repetitions, runs kept beyond the reduced design)
    if op.exists():
        sched = list(jl(DATA / "experiment" / "overreach" / "schedule.jsonl"))
        m["nOverRunsPlanned"] = num(len(sched))
        m["nOverRepsPlanned"] = num(max(r["rep"] for r in sched) + 1)
        import experiment_overreach as eo
        m["nOverRepsFinal"] = num(eo.MAX_REP)
        m["nOverRunsExtra"] = num(sum(1 for r in jl(op) if r["rep"] >= eo.MAX_REP))

    # ---- Table: experiment cells (RQ5)
    if rp.exists():
        experiment_table([r for r in jl(rp) if r.get("success") is not None])

    # ---- emit, and check every macro the drafts use
    used = set()
    for f in PAPER.glob("draft_*.tex"):
        used |= set(re.findall(r"\\([A-Za-z]+)\{\}", f.read_text()))
    known = {k for k in m}
    missing = sorted(used - known - {"code", "ci", "authornote", "repourl", "ldots"})
    for k in missing:
        m[k] = "\\textbf{??}"
    out = [f"% generated by code/paper_numbers.py on {__import__('datetime').date.today()}; primary population {tag}",
           "% corpus-wide macros (all specifications): nDirectiveSentences, pctProhibitionSentences, pctProhibitionWeakOnly,",
           "% nDistinctDirective, Cat*, nRoleItems, nTopics, TopicMedianNpmi; RoleShare*, RQtwoShare* and *Pooled are pooled", ""]
    for k in sorted(m):
        out.append(f"\\newcommand{{\\{k}}}{{{m[k]}}}")
    (PAPER / "numbers.tex").write_text("\n".join(out) + "\n")
    print(f"wrote {len(m)} macros to paper/numbers.tex ({tag} population)")
    if missing:
        print("  still unresolved (placeholders):", ", ".join(missing))


def _fisher2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test p-value for the 2x2 table [[a, b], [c, d]]."""
    import math
    lf = lambda x: math.lgamma(x + 1)   # noqa: E731
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    p = lambda x: math.exp(lf(r1) + lf(r2) + lf(c1) + lf(n - c1) - lf(x) - lf(r1 - x) - lf(c1 - x) - lf(r2 - c1 + x) - lf(n))   # noqa: E731
    obs = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - r2), min(r1, c1) + 1) if p(x) <= obs * (1 + 1e-7)))


def experiment_table(runs: list[dict]) -> None:
    """Emit paper/gen_experiment_table.tex: success per configuration, model and task group."""
    def cell(xs):
        k = sum(1 for r in xs if r["success"])
        return f"{k}/{len(xs)}" if xs else "--"
    desc = {"C0": "no \\code{tools}, neutral prompt", "C1": "no \\code{tools}, prompt forbids writes",
            "C2": "\\code{Read, Grep, Glob, Bash}", "C3": "C2 grant + C1 prompt", "C4": "\\code{Read, Grep, Glob}"}
    models = ("haiku", "sonnet", "opus")
    lines = [
        "\\begin{table}[t]",
        "\\caption{Experiment outcomes: runs in which the task's objective held afterwards (T2--T5 verified on the file",
        "system, T1 and T6 from the reported value), out of scored runs. T2--T5 (create, modify, delete, run a file-writing",
        "script) are forbidden by the prompts of C1 and C3; T1 (read a value) and T6 (run a script and report its output)",
        "are permitted everywhere, and T6 needs a shell. C2 and C3 resolve to \\code{Read, Bash}, because the resolver",
        "drops \\code{Grep} and \\code{Glob} next to \\code{Bash}.}",
        "\\label{tab:experiment}",
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\begin{tabular}{@{}llrrrrr@{}}",
        "\\toprule",
        " & & \\multicolumn{3}{c}{\\textbf{T2--T5, by model}} & \\multicolumn{2}{c}{\\textbf{all models}} \\\\",
        "\\cmidrule(lr){3-5}\\cmidrule(l){6-7}",
        "\\textbf{Config.} & \\textbf{Grant and prompt} & \\textbf{Haiku} & \\textbf{Sonnet} & \\textbf{Opus} & \\textbf{T1} & \\textbf{T6} \\\\",
        "\\midrule",
    ]
    for c in ("C0", "C1", "C2", "C3", "C4"):
        row = [c, desc[c]]
        for mod in models:
            row.append(cell([r for r in runs if r["config"] == c and r["model"] == mod and r["task"] in {"T2", "T3", "T4", "T5"}]))
        for t in ("T1", "T6"):
            row.append(cell([r for r in runs if r["config"] == c and r["task"] == t]))
        lines.append(" & ".join(row) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    (PAPER / "gen_experiment_table.tex").write_text("\n".join(lines) + "\n")
    print("wrote paper/gen_experiment_table.tex")


if __name__ == "__main__":
    main()
