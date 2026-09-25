#!/usr/bin/env python3
"""Engineered-project curation, exactly as fixed in ``annotation/engineered_filter_protocol.md``.

    python3 code/curation.py          # -> data/v2/engineered.jsonl.gz and a step-by-step removal report

Inputs: data/repometa_v2.jsonl.gz (``repometa_v2.py merge``), data/v2/agents.jsonl.gz, and, when present, the README
labels in data/v2/labels/readme_sonnet.jsonl.gz. Without README labels only E1 is computed.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
V2 = DATA / "v2"
SNAPSHOT = datetime.fromisoformat("2026-08-28T23:59:59+00:00")

MIN_COMMITS = 50
MIN_ACTIVE_MONTHS = 3
RECENT_MONTHS = 6
MIN_CODE_BYTES = 10_000


def months_before(n: int) -> set[str]:
    y, m = SNAPSHOT.year, SNAPSHOT.month
    out = set()
    for _ in range(n):
        out.add(f"{y:04d}{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out


def lifecycle(monthly: dict[str, int]) -> dict:
    active = sorted(k for k, v in monthly.items() if v)
    total = sum(monthly.values())
    if not active:
        return {"active_months": 0, "single_burst": False, "sustained": False, "dormant": True, "observed_commits": 0}
    first = active[0]
    span = [k for k in sorted(monthly) if k >= first]
    peak = max(monthly.values())
    recent = months_before(RECENT_MONTHS)
    return {"active_months": len(active), "observed_commits": total,
            "single_burst": total > 0 and peak / total >= 0.8,
            "sustained": len(active) >= 3 and len(active) >= 0.5 * len(span),
            "dormant": not any(monthly.get(k) for k in recent)}


def main() -> None:
    spec_repos = collections.Counter()
    with gzip.open(V2 / "agents.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("available") and r.get("is_spec"):
                spec_repos[r["repo"]] += 1
    # Stage B labels come from the bulk rater (Haiku); a Sonnet file, when present, is the reliability sample and
    # takes precedence for the repositories it covers.
    labels = {}
    for rater in ("haiku", "sonnet"):
        lp = V2 / "labels" / f"readme_{rater}.jsonl.gz"
        if lp.exists():
            with gzip.open(lp, "rt") as fh:
                for line in fh:
                    r = json.loads(line)
                    labels[r["id"]] = r
            print(f"  README labels: {lp.name}")
    out = []
    with gzip.open(DATA / "repometa_v2.jsonl.gz", "rt") as fh:
        for line in fh:
            m = json.loads(line)
            repo = m["frame_repo"]
            if repo not in spec_repos:
                continue
            ok_meta = m.get("graphql_status") == "ok"
            lc = lifecycle(m.get("monthly_commits") or {})
            a1 = ok_meta and not any([m.get("is_fork"), m.get("archived"), m.get("disabled"), m.get("is_template"),
                                      m.get("mirror"), m.get("empty")])
            a2 = ok_meta and (m.get("commits_to_snapshot") or 0) >= MIN_COMMITS
            a3 = lc["active_months"] >= MIN_ACTIVE_MONTHS
            a4 = not lc["dormant"]
            a5 = (m.get("code_bytes") or 0) >= MIN_CODE_BYTES
            e1 = bool(a1 and a2 and a3 and a4 and a5)
            lid = hashlib.sha1(repo.encode()).hexdigest()[:16]
            cat = (labels.get(lid) or {}).get("category")
            e2 = e1 and cat == "ENGINEERED" if labels else None
            e3 = (e2 and (m.get("contributors") or 0) >= 2 and bool(m.get("license"))) if labels else None
            out.append({"repo": repo, "n_specs": spec_repos[repo], "metadata_ok": ok_meta,
                        "A1_not_fork_archived_template": a1, "A2_commits": a2, "A3_active_months": a3,
                        "A4_recent": a4, "A5_code": a5, **lc,
                        "commits_to_snapshot": m.get("commits_to_snapshot"), "contributors": m.get("contributors"),
                        "stars": m.get("stars"), "license": m.get("license"), "created": m.get("created"),
                        "readme_category": cat, "E1": e1, "E2": e2, "E3": e3, "engineered": e2})
    with gzip.open(V2 / "engineered.jsonl.gz", "wt") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")

    def report(label, keep):
        repos = [r for r in out if keep(r)]
        print(f"  {label:<46s} repos {len(repos):>5,}   specs {sum(r['n_specs'] for r in repos):>6,}")
    print(f"specification-bearing repositories: {len(out):,}")
    report("metadata available", lambda r: r["metadata_ok"])
    report("A1 not fork/archived/template/mirror/empty", lambda r: r["A1_not_fork_archived_template"])
    report("+ A2 >= 50 commits", lambda r: r["A1_not_fork_archived_template"] and r["A2_commits"])
    report("+ A3 >= 3 active months", lambda r: r["A1_not_fork_archived_template"] and r["A2_commits"] and r["A3_active_months"])
    report("+ A4 commit in last 6 months", lambda r: r["A1_not_fork_archived_template"] and r["A2_commits"] and r["A3_active_months"] and r["A4_recent"])
    report("= E1 (+ A5 >= 10 kB code)", lambda r: r["E1"])
    if labels:
        report("E2 = E1 and README ENGINEERED", lambda r: r["E2"])
        report("E3 = E2 and >=2 contributors and licence", lambda r: r["E3"])
        print("  README categories (all spec repos):", dict(collections.Counter(r["readme_category"] for r in out)))
    write_populations_table(out, bool(labels))


def write_populations_table(out: list[dict], have_labels: bool) -> None:
    """Emit paper/gen_populations_table.tex: the curation ladder, one row per screen."""
    def cell(keep) -> tuple[str, str]:
        repos = [r for r in out if keep(r)]
        return f"{len(repos):,}".replace(",", "{,}"), f"{sum(r['n_specs'] for r in repos):,}".replace(",", "{,}")

    a1 = lambda r: r["A1_not_fork_archived_template"]                                          # noqa: E731
    a2 = lambda r: a1(r) and r["A2_commits"]                                                    # noqa: E731
    a3 = lambda r: a2(r) and r["A3_active_months"]                                              # noqa: E731
    a4 = lambda r: a3(r) and r["A4_recent"]                                                     # noqa: E731
    rows = [
        ("ALL", "every repository contributing a specification", lambda r: True),
        ("\\quad A1", "not a fork, archive, template, mirror or empty repository", a1),
        ("\\quad + A2", f"at least {MIN_COMMITS} commits to the snapshot", a2),
        ("\\quad + A3", f"at least {MIN_ACTIVE_MONTHS} months with a commit", a3),
        ("\\quad + A4", "a commit within six months of the snapshot", a4),
        ("E1", f"+ A5: at least {MIN_CODE_BYTES // 1000}\\,kB of source detected by Linguist", lambda r: r["E1"]),
    ]
    if have_labels:
        rows += [("E2", "+ README classified as an engineered software project", lambda r: bool(r["E2"])),
                 ("E3", "+ at least two contributors and a licence", lambda r: bool(r["E3"]))]
    lines = [
        "\\begin{table}[t]",
        "\\caption{The engineered-project screen, fixed in a written protocol before outcomes were joined",
        "(\\S\\ref{sec:curation}). Stage~A is metadata only; Stage~B adds the README classification. The grant, dominance and",
        "mode-gap results are reported under ALL, E1, E2 and E3.}",
        "\\label{tab:populations}",
        "\\footnotesize",
        "\\begin{tabular}{@{}l>{\\raggedright\\arraybackslash}p{5.6cm}rr@{}}",
        "\\toprule",
        "\\textbf{Population} & \\textbf{Screen} & \\textbf{Repositories} & \\textbf{Specifications} \\\\",
        "\\midrule",
    ]
    for name, desc, keep in rows:
        nr, ns = cell(keep)
        lines.append(f"{name} & {desc} & {nr} & {ns} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    path = ROOT / "paper" / "gen_populations_table.tex"
    path.write_text("\n".join(lines))
    print(f"  wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
