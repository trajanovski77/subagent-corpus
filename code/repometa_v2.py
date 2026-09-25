#!/usr/bin/env python3
"""Repository metadata for engineered-project curation and the governance baseline.

    python3 code/repometa_v2.py rest       # core metadata, contributors, branch protection, rulesets
    python3 code/repometa_v2.py graphql    # commit history to the snapshot, lifecycle, PRs, README
    python3 code/repometa_v2.py merge      # -> data/repometa_v2.jsonl.gz

Both collection passes are resumable and cover every repository in the discovery frame
(``data/repos.txt``). Activity measures are bounded at the snapshot (``SNAPSHOT_END``) so that
commits made after collection cannot leak into the curation decision. Stars, contributors and
protection state can only be observed as they are now; that residual mismatch is reported in the
paper.

What each field is for
  history / monthly commits     commit volume and lifecycle archetype (Pickerill et al., 2020)
  contributors, commit authors  community size (Munaiah et al., 2017)
  pulls merged / total          Kalliamvakou et al.'s "most pull requests are never merged" peril
  readme                        input to the LLM engineered-project classifier (Galster et al.)
  protected, rulesets           human-side governance baseline for RQ-governance
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WORK = DATA / "work"
REST_OUT = WORK / "repometa_rest.jsonl"
GQL_OUT = WORK / "repometa_graphql.jsonl"
MERGED = DATA / "repometa_v2.jsonl.gz"

SNAPSHOT_END = "2026-08-28T23:59:59Z"
MONTHS_BACK = 36                      # monthly commit counts for the 36 months before the snapshot
README_CHARS = 8000
README_NAMES = ["README.md", "readme.md", "Readme.md", "README.MD", "README.rst", "README.txt",
                "README", "readme.rst", "docs/README.md"]


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def gh(args: list[str], tries: int = 5, include_headers: bool = False) -> tuple[int, str, str]:
    """Run ``gh api``; return (exit code, stdout, stderr), backing off on rate limits."""
    for attempt in range(tries):
        cmd = ["gh", "api", *( ["-i"] if include_headers else []), *args]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        low = (p.stderr + (p.stdout[:400] if p.returncode else "")).lower()
        if p.returncode and ("rate limit" in low or "secondary" in low or "abuse" in low
                             or "502" in low or "503" in low or "504" in low or "timed out" in low):
            wait = 60 * (attempt + 1)
            log(f"  transient/rate-limit; sleeping {wait}s")
            time.sleep(wait)
            continue
        return p.returncode, p.stdout, p.stderr
    return 1, "", "gave up"


def split_headers(raw: str) -> tuple[dict[str, str], str]:
    head, _, body = raw.partition("\r\n\r\n")
    if not body and "\n\n" in raw:
        head, _, body = raw.partition("\n\n")
    headers = {}
    for line in head.splitlines()[1:]:
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return headers, body


def frame() -> list[str]:
    return [l.strip() for l in (DATA / "repos.txt").read_text().splitlines() if l.strip()]


def done(path: Path) -> set[str]:
    out = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.add(json.loads(line)["frame_repo"])
            except (json.JSONDecodeError, KeyError):
                pass
    return out


# ----------------------------------------------------------------------------------- REST pass
def rest_one(repo: str) -> dict:
    rec: dict = {"frame_repo": repo, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    rc, out, err = gh(["-X", "GET", f"repos/{repo}"])
    if rc:
        rec["status"] = "not-found" if "404" in err or "Not Found" in out else "error"
        return rec
    r = json.loads(out)
    rec.update(status="ok", repo=r["full_name"], renamed=r["full_name"].lower() != repo.lower(),
               stars=r.get("stargazers_count"), forks=r.get("forks_count"), is_fork=r.get("fork"),
               archived=r.get("archived"), disabled=r.get("disabled"), is_template=r.get("is_template"),
               created=r.get("created_at"), pushed=r.get("pushed_at"), size_kb=r.get("size"),
               language=r.get("language"), license=(r.get("license") or {}).get("spdx_id"),
               topics=r.get("topics") or [], has_issues=r.get("has_issues"),
               open_issues=r.get("open_issues_count"), subscribers=r.get("subscribers_count"),
               description=r.get("description"), homepage=r.get("homepage"),
               default_branch=r.get("default_branch"), owner_type=(r.get("owner") or {}).get("type"),
               mirror=bool(r.get("mirror_url")))
    full = r["full_name"]

    # contributors: the page count of a 1-per-page listing is the contributor count
    rc, out, err = gh(["-X", "GET", f"repos/{full}/contributors?per_page=1&anon=true"], include_headers=True)
    if rc:
        rec["contributors"] = None
        rec["contributors_note"] = "too-large" if "too large" in (out + err).lower() else "error"
    else:
        headers, body = split_headers(out)
        m = re.search(r'[?&]page=(\d+)>;\s*rel="last"', headers.get("link", ""))
        if m:
            rec["contributors"] = int(m.group(1))
        else:
            try:
                rec["contributors"] = len(json.loads(body)) if body.strip() else 0
            except json.JSONDecodeError:
                rec["contributors"] = 0
    b = rec["default_branch"]
    if b:
        rc, out, _ = gh(["-X", "GET", f"repos/{full}/branches/{b}"])
        rec["branch_protected"] = json.loads(out).get("protected") if not rc else None
        rc, out, _ = gh(["-X", "GET", f"repos/{full}/rules/branches/{b}"])
        if not rc:
            rules = json.loads(out)
            rec["ruleset_rule_types"] = sorted({x.get("type") for x in rules if isinstance(x, dict)})
        else:
            rec["ruleset_rule_types"] = None
    return rec


def rest_pass() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    have = done(REST_OUT)
    todo = [r for r in frame() if r not in have]
    log(f"REST pass: {len(have):,} done, {len(todo):,} to go")
    with open(REST_OUT, "a") as fh:
        for i, repo in enumerate(todo, 1):
            fh.write(json.dumps(rest_one(repo)) + "\n")
            fh.flush()
            if i % 100 == 0:
                log(f"  {i:,}/{len(todo):,}")
            time.sleep(0.55)          # ~4 calls per repo stays under 5,000 core requests per hour


# -------------------------------------------------------------------------------- GraphQL pass
def month_windows(end_iso: str, n: int) -> list[tuple[str, str, str]]:
    end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    y, m = end.year, end.month
    out = []
    for _ in range(n):
        start = f"{y:04d}-{m:02d}-01T00:00:00Z"
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        stop = f"{ny:04d}-{nm:02d}-01T00:00:00Z" if f"{ny:04d}-{nm:02d}" <= end_iso[:7] else end_iso
        out.append((f"m{y:04d}{m:02d}", start, stop))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out


def gql_fragment(alias: str, full: str) -> str:
    owner, name = full.split("/", 1)
    months = " ".join(f'{a}: history(since: "{s}", until: "{u}") {{ totalCount }}'
                      for a, s, u in month_windows(SNAPSHOT_END, MONTHS_BACK))
    readmes = " ".join(f'rd{i}: object(expression: "HEAD:{n}") {{ ... on Blob {{ text byteSize }} }}'
                       for i, n in enumerate(README_NAMES))
    return f'''{alias}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
      nameWithOwner isFork isArchived isTemplate isMirror isEmpty diskUsage createdAt pushedAt
      stargazerCount forkCount
      watchers {{ totalCount }}
      issues {{ totalCount }}
      pullRequests {{ totalCount }}
      mergedPRs: pullRequests(states: MERGED) {{ totalCount }}
      releases {{ totalCount }}
      languages(first: 12, orderBy: {{field: SIZE, direction: DESC}}) {{ totalSize edges {{ size node {{ name }} }} }}
      codeowners1: object(expression: "HEAD:.github/CODEOWNERS") {{ ... on Blob {{ byteSize }} }}
      codeowners2: object(expression: "HEAD:CODEOWNERS") {{ ... on Blob {{ byteSize }} }}
      codeowners3: object(expression: "HEAD:docs/CODEOWNERS") {{ ... on Blob {{ byteSize }} }}
      dependabot: object(expression: "HEAD:.github/dependabot.yml") {{ ... on Blob {{ byteSize }} }}
      securityPolicy: object(expression: "HEAD:SECURITY.md") {{ ... on Blob {{ byteSize }} }}
      {readmes}
      defaultBranchRef {{ name target {{ ... on Commit {{
        total: history(until: "{SNAPSHOT_END}") {{ totalCount }}
        recent: history(first: 100, until: "{SNAPSHOT_END}") {{ nodes {{ committedDate author {{ email user {{ login }} }} }} }}
        {months}
      }} }} }}
    }}'''


def parse_gql(frame_repo: str, node: dict | None) -> dict:
    rec: dict = {"frame_repo": frame_repo, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if node is None:
        rec["status"] = "unresolved"
        return rec
    tgt = ((node.get("defaultBranchRef") or {}).get("target")) or {}
    recent = (tgt.get("recent") or {}).get("nodes") or []
    authors = set()
    for c in recent:
        a = c.get("author") or {}
        authors.add(((a.get("user") or {}).get("login")) or (a.get("email") or "").lower())
    months = {k[1:]: v["totalCount"] for k, v in tgt.items() if re.fullmatch(r"m\d{6}", k) and v}
    readme = None
    for i in range(len(README_NAMES)):
        blob = node.get(f"rd{i}")
        if blob and blob.get("text"):
            readme = {"name": README_NAMES[i], "bytes": blob.get("byteSize"), "text": blob["text"][:README_CHARS]}
            break
    langs = node.get("languages") or {}
    rec.update(
        status="ok", repo=node["nameWithOwner"], is_fork=node["isFork"], archived=node["isArchived"],
        is_template=node["isTemplate"], mirror=node["isMirror"], empty=node["isEmpty"],
        disk_kb=node["diskUsage"], created=node["createdAt"], pushed=node["pushedAt"],
        stars=node["stargazerCount"], forks=node["forkCount"], watchers=node["watchers"]["totalCount"],
        issues=node["issues"]["totalCount"], pulls=node["pullRequests"]["totalCount"],
        pulls_merged=node["mergedPRs"]["totalCount"], releases=node["releases"]["totalCount"],
        languages={e["node"]["name"]: e["size"] for e in langs.get("edges") or []},
        code_bytes=langs.get("totalSize"),
        codeowners=any(node.get(k) for k in ("codeowners1", "codeowners2", "codeowners3")),
        dependabot=bool(node.get("dependabot")), security_policy=bool(node.get("securityPolicy")),
        default_branch=(node.get("defaultBranchRef") or {}).get("name"),
        commits_to_snapshot=(tgt.get("total") or {}).get("totalCount"),
        recent_commit_authors=len(authors - {""}), recent_commits_seen=len(recent),
        first_recent_commit=min((c["committedDate"] for c in recent), default=None),
        last_commit=max((c["committedDate"] for c in recent), default=None),
        monthly_commits=months, readme=readme)
    return rec


def graphql_pass(batch_size: int = 6) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    have = done(GQL_OUT)
    # prefer the current name found by the REST pass, so renamed repositories resolve
    current = {}
    if REST_OUT.exists():
        for line in REST_OUT.read_text().splitlines():
            r = json.loads(line)
            if r.get("status") == "ok":
                current[r["frame_repo"]] = r["repo"]
    todo = [r for r in frame() if r not in have]
    log(f"GraphQL pass: {len(have):,} done, {len(todo):,} to go")
    with open(GQL_OUT, "a") as fh:
        i = 0
        while i < len(todo):
            chunk = todo[i:i + batch_size]
            query = "query { rateLimit { cost remaining resetAt } " + " ".join(
                gql_fragment(f"r{k}", current.get(repo, repo)) for k, repo in enumerate(chunk)) + " }"
            rc, out, err = gh(["graphql", "-f", f"query={query}"])
            try:
                payload = json.loads(out) if out.strip() else {}
            except json.JSONDecodeError:
                payload = {}
            data = payload.get("data")
            if data is None:
                if batch_size > 1 and len(chunk) > 1:
                    log(f"  batch failed ({(err or out)[:120].strip()}); retrying one by one")
                    for repo in chunk:
                        q1 = "query { " + gql_fragment("r0", current.get(repo, repo)) + " }"
                        _, o1, _ = gh(["graphql", "-f", f"query={q1}"])
                        try:
                            d1 = (json.loads(o1) if o1.strip() else {}).get("data") or {}
                        except json.JSONDecodeError:
                            d1 = {}
                        fh.write(json.dumps(parse_gql(repo, d1.get("r0"))) + "\n")
                    fh.flush()
                    i += len(chunk)
                    continue
                log(f"  request failed, sleeping 60s: {(err or out)[:160].strip()}")
                time.sleep(60)
                continue
            for k, repo in enumerate(chunk):
                fh.write(json.dumps(parse_gql(repo, data.get(f"r{k}"))) + "\n")
            fh.flush()
            i += len(chunk)
            rl = data.get("rateLimit") or {}
            if i % 300 < batch_size:
                log(f"  {i:,}/{len(todo):,}  cost {rl.get('cost')} remaining {rl.get('remaining')}")
            if rl.get("remaining", 5000) < 200:
                reset = datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
                wait = max(0, (reset - datetime.now(timezone.utc)).total_seconds()) + 10
                log(f"  GraphQL budget low; sleeping {wait:.0f}s")
                time.sleep(wait)


# ------------------------------------------------------------------------------------- merge
def merge() -> None:
    rest = {json.loads(l)["frame_repo"]: json.loads(l) for l in REST_OUT.read_text().splitlines()}
    gql = {json.loads(l)["frame_repo"]: json.loads(l) for l in GQL_OUT.read_text().splitlines()}
    n = 0
    with gzip.open(MERGED, "wt") as fh:
        for repo in frame():
            r, g = rest.get(repo, {}), gql.get(repo, {})
            rec = {"frame_repo": repo, "rest_status": r.get("status"), "graphql_status": g.get("status")}
            for src in (g, r):                      # REST wins on overlapping keys (it is newer)
                for k, v in src.items():
                    if k not in ("status", "at", "frame_repo"):
                        rec[k] = v
            rec["collected_at"] = max(filter(None, [r.get("at"), g.get("at")]), default=None)
            fh.write(json.dumps(rec) + "\n")
            n += 1
    log(f"merged {n:,} repositories into {MERGED.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["rest", "graphql", "merge"])
    a = ap.parse_args()
    {"rest": rest_pass, "graphql": graphql_pass, "merge": merge}[a.mode]()
