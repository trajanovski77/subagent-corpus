#!/usr/bin/env python3
"""Artifact-runtime drift: was a removed tool name still valid when the specification was written?

    python3 code/drift.py removals     # removal releases and dates from the executed tool-pool history
    python3 code/drift.py dates        # first commit touching each affected file (GitHub GraphQL, resumable)
    python3 code/drift.py report

A specification that names a tool the pinned build no longer resolves is either (a) drift, written while the name
was valid and never updated, or (b) a stale copy, written after the name had already been removed. The two call for
different explanations and different fixes, and version 1 of the paper could not tell them apart. The removal date
of each name comes from ``data/v2/oracles/tool_pool_history.jsonl`` (the default tool pool of 48 releases, observed by
execution); the authoring date is the committer date of the earliest commit on the default branch that touches the
file, bounded by the snapshot.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "data" / "v2"
ORA = V2 / "oracles"
OUT = V2 / "drift_first_commits.jsonl"
SNAP = "2026-08-28T23:59:59Z"
NAMES = ["TodoRead", "NotebookRead", "LS", "KillBash", "MultiEdit", "SlashCommand", "exit_plan_mode"]


def npm_dates() -> dict[str, str]:
    out = subprocess.run(["npm", "view", "@anthropic-ai/claude-code", "time", "--json"], capture_output=True, text=True).stdout
    return json.loads(out)


def vkey(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def removals() -> dict[str, dict]:
    dates = npm_dates()
    hist = [json.loads(l) for l in (ORA / "tool_pool_history.jsonl").read_text().splitlines() if json.loads(l).get("ok")]
    hist.sort(key=lambda r: vkey(r["requested"]))
    res = {}
    for name in NAMES:
        present = [r["requested"] for r in hist if name in (r.get("tools") or [])]
        if not present:
            continue
        last = max(present, key=vkey)
        later = [r["requested"] for r in hist if vkey(r["requested"]) > vkey(last)]
        first_absent = min(later, key=vkey) if later else None
        res[name] = {"last_release_with_name": last, "last_date": dates.get(last, "")[:10],
                     "first_release_without_name": first_absent,
                     "removal_date_upper": dates.get(first_absent, "")[:10] if first_absent else None}
    (V2 / "drift_removals.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


def affected() -> list[dict]:
    rows = []
    with gzip.open(V2 / "spec_table.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r["grant"] == "explicit" and set(r["requested"]) & set(NAMES):
                rows.append({"repo": r["repo"], "path": r["path"], "names": sorted(set(r["requested"]) & set(NAMES))})
    return rows


def gh_graphql(query: str) -> dict:
    for attempt in range(6):
        p = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"], capture_output=True, text=True, timeout=240)
        try:
            d = json.loads(p.stdout) if p.stdout.strip() else {}
        except json.JSONDecodeError:
            d = {}
        if d.get("data") is not None:
            return d
        if "rate limit" in (p.stderr + p.stdout).lower() or "secondary" in (p.stderr + p.stdout).lower():
            time.sleep(60 * (attempt + 1))
            continue
        time.sleep(5)
    return {}


def dates(batch: int = 25) -> None:
    items = affected()
    done = set()
    if OUT.exists():
        done = {(json.loads(l)["repo"], json.loads(l)["path"]) for l in OUT.read_text().splitlines()}
    todo = [i for i in items if (i["repo"], i["path"]) not in done]
    print(f"{len(items):,} affected files, {len(todo):,} to date", flush=True)
    with open(OUT, "a") as fh:
        for b in range(0, len(todo), batch):
            chunk = todo[b:b + batch]
            parts = []
            for k, it in enumerate(chunk):
                owner, name = it["repo"].split("/", 1)
                parts.append(f'''r{k}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ defaultBranchRef {{ target {{ ... on Commit {{
                  h: history(path: {json.dumps(it["path"])}, first: 1, until: "{SNAP}") {{ totalCount pageInfo {{ startCursor }} nodes {{ committedDate }} }} }} }} }} }}''')
            d1 = gh_graphql("query { " + " ".join(parts) + " }").get("data") or {}
            second, meta = [], {}
            for k, it in enumerate(chunk):
                h = ((((d1.get(f"r{k}") or {}).get("defaultBranchRef") or {}).get("target") or {}).get("h")) or {}
                total = h.get("totalCount")
                nodes = h.get("nodes") or []
                meta[k] = {"total": total, "latest": nodes[0]["committedDate"] if nodes else None}
                if total and total > 1 and (h.get("pageInfo") or {}).get("startCursor"):
                    oid = h["pageInfo"]["startCursor"].split(" ")[0]
                    owner, name = it["repo"].split("/", 1)
                    second.append(f'''s{k}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ defaultBranchRef {{ target {{ ... on Commit {{
                      h: history(path: {json.dumps(it["path"])}, first: 1, until: "{SNAP}", after: "{oid} {total - 2}") {{ nodes {{ committedDate }} }} }} }} }} }}''')
            d2 = gh_graphql("query { " + " ".join(second) + " }").get("data") or {} if second else {}
            for k, it in enumerate(chunk):
                first = meta[k]["latest"] if meta[k]["total"] == 1 else None
                if meta[k]["total"] and meta[k]["total"] > 1:
                    h2 = ((((d2.get(f"s{k}") or {}).get("defaultBranchRef") or {}).get("target") or {}).get("h")) or {}
                    n2 = h2.get("nodes") or []
                    first = n2[0]["committedDate"] if n2 else None
                fh.write(json.dumps({**it, "commits_touching": meta[k]["total"], "first_commit": first,
                                     "last_commit": meta[k]["latest"]}) + "\n")
            fh.flush()
            if (b // batch) % 20 == 0:
                print(f"  {b + len(chunk):,}/{len(todo):,}", flush=True)


def report() -> None:
    rem = json.loads((V2 / "drift_removals.json").read_text())
    rows = [json.loads(l) for l in OUT.read_text().splitlines()]
    by_name = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        for n in r["names"]:
            if n not in rem or not r.get("first_commit"):
                by_name[n]["undated"] += 1
                continue
            cutoff = rem[n]["removal_date_upper"] or "9999"
            by_name[n]["written_before_removal" if r["first_commit"][:10] < cutoff else "written_after_removal"] += 1
    for n, c in by_name.items():
        tot = sum(c.values())
        print(f"  {n:<14s} removed by {rem.get(n, {}).get('first_release_without_name')} ({rem.get(n, {}).get('removal_date_upper')}): "
              f"{dict(c)}  after-removal share {100*c['written_after_removal']/max(1, tot - c['undated']):.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["removals", "dates", "report"])
    a = ap.parse_args()
    if a.what == "removals":
        print(json.dumps(removals(), indent=1))
    elif a.what == "dates":
        dates()
    else:
        report()
