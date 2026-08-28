#!/usr/bin/env python3
"""
collect.py -- reproducible collection of subagent specifications from public GitHub.

This is the single entry point for the whole corpus. It is idempotent and resumable:
re-running it continues from whatever is already on disk and re-fetches nothing.

WHY IT LOOKS LIKE THIS
----------------------
GitHub's code-search API is the only public index of file *contents*, and it has two
properties that shape everything below:

  (1) it returns at most 1,000 results per query, and only the first 10 pages of 100; and
  (2) its reported `total_count` is unreliable for large result sets.

So we never treat a single query as a sample frame. Instead:

  STAGE 1  Partition the query space by FILE SIZE into bands and run one query per band.
           Record `total_count` for every band, so truncation is measurable rather than
           invisible. Use the results only to DISCOVER REPOSITORY NAMES.
  STAGE 2  For each discovered repository, call the Git Trees API once. That returns the
           repository's complete file list in a single request and is not subject to the
           search cap, so within a discovered repository our file inventory is exhaustive.
  STAGE 3  Fetch the raw bytes of every agent file found in stage 2 and parse frontmatter.

Stage 2 is what makes the per-repository census exhaustive. Stage 1 only decides WHICH
repositories we look at, and its biases are documented in provenance.json and in the paper.

WHAT IS AND IS NOT CLAIMED
--------------------------
This yields a convenience sample of repositories, not a probability sample. Code search
excludes forks and indexes only default branches. Discovery is file-level, so a repository
with many agent files has more chances to surface than one with few: the repository sample
is size-biased, and the paper says so. Prevalence figures are within-repository proportions
and are far less affected by that bias than the team-size distribution is.

USAGE
-----
    gh auth login                 # once; the script shells out to `gh api`
    python3 collect.py            # runs all three stages, resumable
    python3 collect.py --stage 1  # or run one stage at a time
    python3 collect.py --provenance-only --snapshot 2026-08-27/2026-08-28   # manifest from the archive

OUTPUT (written to ../data/)
----------------------------
    repos.txt            discovered repository names, one per line
    partitions.jsonl     one record per search query: band, reported total, retrieved, page count
    trees.jsonl          one record per repository: its complete config-file inventory
    agents.jsonl         one record per agent file: metadata + parsed frontmatter
    provenance.json      run manifest: timestamps, versions, counts, truncation summary

The archived snapshot ships these files gzipped (agents.jsonl.gz, trees.jsonl.gz); the
analysis reads either form through parsing.load_records().
"""

import argparse, json, os, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request
import concurrent.futures as cf
from datetime import datetime, timezone

BASE = pathlib.Path(__file__).resolve().parent
DATA = BASE.parent / "data"          # every output lands in the data/ directory
DATA.mkdir(exist_ok=True)
REPOS, PARTS = DATA / "repos.txt", DATA / "partitions.jsonl"
TREES, AGENTS = DATA / "trees.jsonl", DATA / "agents.jsonl"
PROV = DATA / "provenance.json"

QUERY = "path:.claude/agents extension:md"

# Size bands in bytes. Chosen so that most bands fall under the reachable result ceiling;
# bands that do not are recorded as truncated in partitions.jsonl rather than silently cut.
BANDS = [(0,150),(151,300),(301,450),(451,600),(601,750),(751,900),(901,1100),(1101,1300),
         (1301,1500),(1501,1750),(1751,2000),(2001,2300),(2301,2600),(2601,3000),(3001,3400),
         (3401,3900),(3901,4500),(4501,5200),(5201,6000),(6001,7000),(7001,8200),(8201,9600),
         (9601,11500),(11501,14000),(14001,18000),(18001,25000),(25001,40000),(40001,400000)]

PAGES_PER_BAND = 10          # API maximum; 1,000 results per band
SEARCH_SLEEP   = 6.5         # code search is ~10 req/min
TREE_SLEEP     = 0.15        # core API is 5,000 req/hr
FETCH_THREADS  = 24

# Files we keep from each repository tree. Agent specs are the study object; the rest give
# the co-occurrence analysis (which other configuration artifacts the repository ships).
KEEP = re.compile(
    r'(^|/)\.claude/(agents|commands|skills)/.*\.md$'
    r'|(^|/)\.claude/settings(\.local)?\.json$'
    r'|(^|/)CLAUDE\.md$|(^|/)AGENTS\.md$|(^|/)\.mcp\.json$|(^|/)SKILL\.md$'
    r'|(^|/)\.claude-plugin/|(^|/)\.github/workflows/.*\.ya?ml$')
IS_AGENT = re.compile(r'(^|/)\.claude/agents/.*\.md$')


def log(msg):
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def gh(args, tries=5):
    """Call `gh api`, backing off on rate limits. Returns parsed JSON or None."""
    for attempt in range(tries):
        p = subprocess.run(["gh", "api"] + args, capture_output=True, text=True, timeout=180)
        if p.returncode == 0:
            try:
                return json.loads(p.stdout)
            except json.JSONDecodeError:
                return None
        err = p.stderr.lower()
        if "rate limit" in err or "secondary" in err or "403" in err:
            wait = 25 * (attempt + 1)
            log(f"  rate limited, sleeping {wait}s")
            time.sleep(wait)
            continue
        if "422" in err or "404" in err:
            return None
        time.sleep(4)
    return None


def read_lines(path):
    return [l for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


# --------------------------------------------------------------- stage 1: discovery
def stage1():
    repos = set(read_lines(REPOS))
    done_bands = {json.loads(l)["band"] for l in read_lines(PARTS)}
    log(f"stage 1: discovery. {len(repos)} repositories already known, "
        f"{len(done_bands)}/{len(BANDS)} bands already queried")

    with open(PARTS, "a") as pf:
        for lo, hi in BANDS:
            band = f"{lo}..{hi}"
            if band in done_bands:
                continue
            q = f"{QUERY} size:{band}"
            first = gh(["-X", "GET", "search/code", "-f", f"q={q}", "-f", "per_page=100"])
            time.sleep(SEARCH_SLEEP)
            if first is None:
                log(f"  band {band}: query failed, skipped")
                continue
            total = first.get("total_count", 0)
            got, pages = set(), 0
            for page in range(1, PAGES_PER_BAND + 1):
                d = first if page == 1 else gh(
                    ["-X", "GET", "search/code", "-f", f"q={q}",
                     "-f", "per_page=100", "-f", f"page={page}"])
                if page > 1:
                    time.sleep(SEARCH_SLEEP)
                if not d or not d.get("items"):
                    break
                pages += 1
                for it in d["items"]:
                    got.add(it["repository"]["full_name"])
                if len(d["items"]) < 100:
                    break
            repos |= got
            # `truncated` is the honest record: reported total exceeded what the API would serve.
            rec = {"band": band, "reported_total": total, "pages_retrieved": pages,
                   "distinct_repos_here": len(got),
                   "truncated": bool(total > PAGES_PER_BAND * 100),
                   "at": datetime.now(timezone.utc).isoformat()}
            pf.write(json.dumps(rec) + "\n"); pf.flush()
            REPOS.write_text("\n".join(sorted(repos)))
            log(f"  band {band:>14s}  reported {total:>6}  pages {pages:>2}  "
                f"{'TRUNCATED' if rec['truncated'] else 'complete '}  running total {len(repos)}")
    log(f"stage 1 done: {len(repos)} repositories")


# --------------------------------------------------------------- stage 2: repository trees
def stage2():
    repos = read_lines(REPOS)
    done = {json.loads(l)["repo"] for l in read_lines(TREES)}
    todo = [r for r in repos if r not in done]
    log(f"stage 2: trees. {len(done)} done, {len(todo)} to fetch")
    with open(TREES, "a") as f:
        for i, repo in enumerate(todo, 1):
            d = gh(["-X", "GET", f"repos/{repo}/git/trees/HEAD", "-f", "recursive=1"], tries=2)
            time.sleep(TREE_SLEEP)
            if not d or "tree" not in d:
                continue
            cfg = [{"p": t["path"], "s": t.get("size"), "sha": t.get("sha"), "mode": t.get("mode")}
                   for t in d["tree"] if t["type"] == "blob" and KEEP.search(t["path"])]
            f.write(json.dumps({"repo": repo, "n_files": len(d["tree"]),
                                "truncated": d.get("truncated", False), "cfg": cfg}) + "\n")
            f.flush()
            if i % 200 == 0:
                log(f"  {i}/{len(todo)}")
    log("stage 2 done")


# --------------------------------------------------------------- stage 3: fetch + parse
FM = re.compile(r'\A﻿?---\s*\n(.*?)\n---\s*(\n|$)', re.S)


def norm_tools(v):
    """Comma is the real separator. A parenthesised specifier such as Bash(npm run build)
    must not be split on its inner spaces."""
    if v is None:
        return None
    if isinstance(v, list):
        items = [str(x).strip() for x in v]
    elif isinstance(v, str):
        t = v.strip()
        if not t:
            return []
        if t in ("*", "all"):
            return ["*"]
        items = ([x.strip() for x in t.split(",")] if "," in t
                 else re.findall(r'[A-Za-z_][\w.-]*\([^)]*\)|\S+', t))
    else:
        items = [str(v)]
    return [x for x in items if x]


def fetch_one(job):
    import hashlib, yaml
    repo, path = job
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{urllib.parse.quote(path)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "subagent-corpus/1.0"})
        raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
    except Exception:
        return None
    rec = {"repo": repo, "path": path, "bytes": len(raw),
           "hash": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]}
    m = FM.match(raw)
    if not m:
        rec["fm_error"] = "no-frontmatter"
        rec["body_head"] = raw.strip()[:400]
        return rec
    body = raw[m.end():]
    rec["body_chars"] = len(body.strip())
    rec["body_head"] = body.strip()[:400]
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        rec["fm_error"] = "yaml-error"
        return rec
    if not isinstance(fm, dict):
        rec["fm_error"] = "fm-not-dict"
        return rec
    # `name` and `description` occasionally parse as non-strings; keep them raw and let the
    # analysis coerce, so the corpus records what was actually written.
    for k in ("name", "description", "model", "permissionMode", "maxTurns",
              "memory", "background", "isolation", "color", "effort"):
        if k in fm:
            rec[k] = fm[k]
    rec["tools_raw"] = fm.get("tools")
    rec["tools"] = norm_tools(fm.get("tools"))
    rec["disallowedTools"] = norm_tools(fm.get("disallowedTools"))
    rec["skills"] = norm_tools(fm.get("skills"))
    rec["mcpServers"] = norm_tools(fm.get("mcpServers"))
    rec["has_hooks"] = bool(fm.get("hooks"))
    rec["fm_keys"] = sorted(str(k) for k in fm.keys())
    return rec


def stage3():
    jobs, seen = [], set()
    for l in read_lines(TREES):
        t = json.loads(l)
        for f in t["cfg"]:
            if IS_AGENT.search("/" + f["p"]):
                k = (t["repo"], f["p"])
                if k not in seen:
                    seen.add(k); jobs.append(k)
    done = {(json.loads(l)["repo"], json.loads(l)["path"]) for l in read_lines(AGENTS)}
    jobs = [j for j in jobs if j not in done]
    log(f"stage 3: fetch. {len(done)} already stored, {len(jobs)} to fetch")
    n = 0
    with open(AGENTS, "a") as out, cf.ThreadPoolExecutor(FETCH_THREADS) as ex:
        for rec in ex.map(fetch_one, jobs):
            if rec:
                out.write(json.dumps(rec) + "\n"); n += 1
            if n and n % 2000 == 0:
                out.flush(); log(f"  {n}/{len(jobs)}")
    log(f"stage 3 done: {n} newly fetched")


# --------------------------------------------------------------- provenance
def _read_jsonl(path):
    """Read a JSON Lines file, falling back to the gzipped archive of the same name."""
    import gzip
    if path.exists():
        return [json.loads(l) for l in read_lines(path)]
    gz = path.with_name(path.name + ".gz")
    if gz.exists():
        with gzip.open(gz, "rt") as fh:
            return [json.loads(l) for l in fh if l.strip()]
    return []


def provenance(snapshot=None, note=None):
    """Write provenance.json from whatever is in data/ (fresh run or archived snapshot).

    Every count is derived from the files themselves, so the manifest can be regenerated from
    the archive:  python3 collect.py --provenance-only --snapshot 2026-08-27/2026-08-28
    """
    parts = _read_jsonl(PARTS)
    agents = _read_jsonl(AGENTS)
    trees = _read_jsonl(TREES)
    meta = _read_jsonl(DATA / "repometa.jsonl")
    specs = [a for a in agents
             if not a.get("fm_error") and a.get("name") and a.get("description")]
    try:
        gh_ver = subprocess.run(["gh", "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    except Exception:
        gh_ver = "unknown"
    stamps = sorted(p["at"] for p in parts if p.get("at"))
    prov = {
        "manifest_written_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot": snapshot,
        "query": QUERY,
        "size_bands": len(BANDS),
        "pages_per_band": PAGES_PER_BAND,
        "bands_queried": len(parts),
        "bands_truncated": sum(1 for p in parts if p["truncated"]),
        "truncated_bands": [p["band"] for p in parts if p["truncated"]],
        "reported_total_sum": sum(p["reported_total"] for p in parts),
        "stage1_queried_utc": [stamps[0], stamps[-1]] if stamps else None,
        "repositories_discovered": len(read_lines(REPOS)),
        "repositories_expanded": len(trees),
        "agent_files_fetched": len(agents),
        "specifications": len(specs),
        "specification_repositories": len({a["repo"] for a in specs}),
        "repometa_repositories": len(meta),
        "repometa_latest_pushed_at": max((m["pushed"] for m in meta if m.get("pushed")), default=None),
        "inclusion_rule": "parseable YAML frontmatter declaring BOTH name and description",
        "tool_build": {"claude_code": "v2.1.233", "commit": "f8d57569aaf3",
                       "note": "all tool behaviour in the paper was observed on this build; "
                               "the tool vocabulary is version-conditional"},
        "python": sys.version.split()[0],
        "gh_cli": gh_ver,
        "known_biases": [
            "code search excludes forks and indexes default branches only",
            "discovery is file-level, so repository inclusion probability rises with agent-file count",
            "bands whose reported_total exceeds 1000 are truncated; see partitions.jsonl",
            "convenience sample: supports no population estimate",
        ],
        "notes": note,
    }
    PROV.write_text(json.dumps(prov, indent=2) + "\n")
    log("provenance written to " + PROV.name)
    for k, v in prov.items():
        if not isinstance(v, (list, dict)):
            log(f"  {k}: {v}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, choices=[1, 2, 3], help="run a single stage")
    ap.add_argument("--provenance-only", action="store_true",
                    help="only (re)write provenance.json from the files in data/")
    ap.add_argument("--snapshot", help="collection dates to record, e.g. 2026-08-27/2026-08-28")
    ap.add_argument("--note", help="free-text note recorded in the manifest")
    a = ap.parse_args()
    if not a.provenance_only:
        if a.stage in (None, 1): stage1()
        if a.stage in (None, 2): stage2()
        if a.stage in (None, 3): stage3()
    provenance(snapshot=a.snapshot, note=a.note)
