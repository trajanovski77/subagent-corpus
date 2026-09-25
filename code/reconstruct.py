#!/usr/bin/env python3
"""Snapshot-exact reconstruction of every configuration file the tree inventory lists.

    python3 code/reconstruct.py            # resumable; writes data/work/blobs.jsonl
    python3 code/reconstruct.py --report   # coverage summary of what is on disk

WHY THIS EXISTS
---------------
Stage 3 of ``collect.py`` fetched agent files from ``raw.githubusercontent.com/<repo>/HEAD`` and
silently dropped every request that raised. Of the 94,899 agent files that the stage-2 tree
inventory lists, only 67,927 were stored, and 1,421 repositories lost every file. It also kept only
the first 400 characters of each body, which rules out any analysis of the prompt text.

This script replaces that stage. The tree inventory records each file's git blob SHA as it stood
at snapshot time, so the exact snapshot content can be fetched by object id rather than from a
moving ``HEAD``. Each object is verified against its SHA (``sha1("blob <len>\\0" + bytes)``), and
every outcome is recorded, including failures, so coverage is measured rather than assumed.

Fetch path: GitHub GraphQL ``repository.object(oid:)`` in batches. A blob whose text is truncated,
binary, not valid UTF-8, or fails verification is re-fetched through the REST git-blob endpoint,
which returns the exact bytes.
"""
from __future__ import annotations

import argparse
import base64
import collections
import gzip
import hashlib
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
OUT = WORK / "blobs.jsonl"

#: Artifact kinds to reconstruct, keyed by the pattern that selects them from the inventory.
KINDS = {
    "agent": re.compile(r"(^|/)\.claude/agents/.*\.md$"),
    "settings": re.compile(r"(^|/)\.claude/settings\.json$"),
    "settings_local": re.compile(r"(^|/)\.claude/settings\.local\.json$"),
    "mcp": re.compile(r"(^|/)\.mcp\.json$"),
    "workflow": re.compile(r"(^|/)\.github/workflows/[^/]+\.ya?ml$"),
}

MAX_BATCH_BYTES = 1_500_000     # GraphQL responses above ~2 MB start to time out
MAX_BATCH_OBJECTS = 120
REST_ONLY_ABOVE = 400_000       # GraphQL truncates large blob text; go straight to REST


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def legacy_hash(text: str) -> str:
    """The ``hash`` field ``collect.py`` stored, so archived records can be matched."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def gh_json(args: list[str], tries: int = 6) -> tuple[dict | None, str]:
    """Run ``gh api``; return (parsed JSON or None, stderr). Backs off on rate limits."""
    err = ""
    for attempt in range(tries):
        p = subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=300)
        err = p.stderr
        out = None
        if p.stdout.strip():
            try:
                out = json.loads(p.stdout)
            except json.JSONDecodeError:
                out = None
        low = err.lower()
        if "rate limit" in low or "secondary" in low or "abuse" in low or "502" in low or "504" in low \
                or "timeout" in low or "timed out" in low:
            wait = 30 * (attempt + 1)
            log(f"  transient error ({err.strip()[:120]}); sleeping {wait}s")
            time.sleep(wait)
            continue
        return out, err
    return None, err


def targets() -> list[dict]:
    """Every file of a reconstructed kind in the snapshot inventory, in a stable order."""
    rows = []
    with gzip.open(DATA / "trees.jsonl.gz", "rt") as fh:
        for line in fh:
            t = json.loads(line)
            for f in t["cfg"]:
                for kind, rx in KINDS.items():
                    if rx.search("/" + f["p"]):
                        rows.append({"repo": t["repo"], "path": f["p"], "sha": f["sha"],
                                     "size": f.get("s") or 0, "kind": kind})
                        break
    return rows


def done_keys() -> set[tuple[str, str]]:
    keys = set()
    if OUT.exists():
        with open(OUT) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    keys.add((r["repo"], r["path"]))
                except (json.JSONDecodeError, KeyError):
                    continue
    return keys


def record(t: dict, data: bytes | None, via: str, status: str) -> dict:
    rec = {"repo": t["repo"], "path": t["path"], "kind": t["kind"], "sha": t["sha"],
           "size": t["size"], "via": via, "status": status,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if data is not None:
        text = data.decode("utf-8", "replace")
        rec.update(sha_ok=git_blob_sha(data) == t["sha"], bytes=len(data),
                   hash=legacy_hash(text), content=text)
    return rec


def graphql_batch(batch: list[dict]) -> dict[tuple[str, str], tuple[bytes | None, str]] | None:
    """Fetch one batch; returns {(repo, path): (bytes or None, reason)}, or None if the request
    itself failed (the caller then splits the batch)."""
    by_repo: dict[str, list[dict]] = collections.defaultdict(list)
    for t in batch:
        by_repo[t["repo"]].append(t)
    parts, alias = [], {}
    for i, (repo, items) in enumerate(by_repo.items()):
        owner, name = repo.split("/", 1)
        objs = []
        for j, t in enumerate(items):
            objs.append(f'f{j}: object(oid: "{t["sha"]}") {{ ... on Blob {{ byteSize isBinary isTruncated text }} }}')
            alias[(f"r{i}", f"f{j}")] = t
        parts.append(f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {" ".join(objs)} }}')
    query = "query { rateLimit { remaining resetAt } " + " ".join(parts) + " }"
    out, err = gh_json(["graphql", "-f", f"query={query}"])
    if not out or "data" not in out:
        log(f"  GraphQL request failed ({len(batch)} objects): {err.strip()[:160]}")
        return None
    data = out.get("data") or {}
    rl = data.get("rateLimit") or {}
    if rl and rl.get("remaining", 5000) < 100:
        reset = datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
        wait = max(0, (reset - datetime.now(timezone.utc)).total_seconds()) + 5
        log(f"  GraphQL budget low ({rl['remaining']}); sleeping {wait:.0f}s")
        time.sleep(wait)
    result: dict[tuple[str, str], tuple[bytes | None, str]] = {}
    for (ra, fa), t in alias.items():
        key = (t["repo"], t["path"])
        if data.get(ra) is None:
            result[key] = (None, "repo-unresolved")
            continue
        node = data[ra].get(fa)
        if node is None:
            result[key] = (None, "object-missing")
        elif node.get("isBinary") or node.get("isTruncated") or node.get("text") is None:
            result[key] = (None, "needs-rest")
        else:
            raw = node["text"].encode("utf-8")
            result[key] = (raw, "ok") if git_blob_sha(raw) == t["sha"] else (None, "needs-rest")
    return result


def fetch_batch(batch: list[dict]) -> dict[tuple[str, str], tuple[bytes | None, str]]:
    """GraphQL with binary splitting on request failure (usually a response-size timeout)."""
    res = graphql_batch(batch)
    if res is not None:
        return res
    if len(batch) == 1:
        return {(batch[0]["repo"], batch[0]["path"]): (None, "needs-rest")}
    mid = len(batch) // 2
    return {**fetch_batch(batch[:mid]), **fetch_batch(batch[mid:])}


_REPO_STATE: dict[str, str | None] = {}


def resolve_repo(repo: str) -> str | None:
    """Current full name of a repository (follows renames), or None if it no longer exists."""
    if repo not in _REPO_STATE:
        out, _ = gh_json(["-X", "GET", f"repos/{repo}"], tries=3)
        _REPO_STATE[repo] = (out or {}).get("full_name")
    return _REPO_STATE[repo]


def rest_blob(t: dict) -> tuple[bytes | None, str]:
    current = resolve_repo(t["repo"])
    if current is None:
        return None, "repo-unavailable"
    out, err = gh_json(["-X", "GET", f"repos/{current}/git/blobs/{t['sha']}"], tries=4)
    if not out or "content" not in out:
        low = err.lower()
        return None, ("object-not-found" if "404" in low or "not found" in low else "rest-error")
    try:
        return base64.b64decode(out["content"]), "ok"
    except (ValueError, TypeError):
        return None, "rest-decode-error"


def run(limit: int | None = None) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    all_targets = targets()
    done = done_keys()
    todo = [t for t in all_targets if (t["repo"], t["path"]) not in done]
    if limit:
        todo = todo[:limit]
    log(f"{len(all_targets):,} files in inventory, {len(done):,} already reconstructed, {len(todo):,} to go")
    rest_queue = [t for t in todo if t["size"] > REST_ONLY_ABOVE]
    gql = [t for t in todo if t["size"] <= REST_ONLY_ABOVE]
    written = 0
    with open(OUT, "a") as fh:
        batch, batch_bytes = [], 0
        for t in gql + [None]:
            flush = t is None or (batch and (batch_bytes + t["size"] > MAX_BATCH_BYTES
                                             or len(batch) >= MAX_BATCH_OBJECTS))
            if flush and batch:
                res = fetch_batch(batch)
                for b in batch:
                    data, why = res.get((b["repo"], b["path"]), (None, "needs-rest"))
                    if data is not None:
                        fh.write(json.dumps(record(b, data, "graphql", "ok")) + "\n")
                        written += 1
                    else:
                        rest_queue.append(b)
                fh.flush()
                before = written - len(batch)
                if written // 5000 > max(before, 0) // 5000:
                    log(f"  graphql: {written:,} written, {len(rest_queue):,} queued for REST")
                batch, batch_bytes = [], 0
            if t is not None:
                batch.append(t)
                batch_bytes += t["size"]
        log(f"graphql pass done: {written:,} written; {len(rest_queue):,} files go through REST")
        for i, t in enumerate(rest_queue, 1):
            data, why = rest_blob(t)
            fh.write(json.dumps(record(t, data, "rest", "ok" if data is not None else why)) + "\n")
            if i % 200 == 0:
                fh.flush()
                log(f"  rest: {i:,}/{len(rest_queue):,}")
            if why != "repo-unavailable":
                time.sleep(0.2)
    log("done")
    report()


def report() -> None:
    inv = targets()
    by = collections.Counter(t["kind"] for t in inv)
    got = collections.Counter()
    status = collections.Counter()
    shaok = collections.Counter()
    if OUT.exists():
        with open(OUT) as fh:
            for line in fh:
                r = json.loads(line)
                status[(r["kind"], r["status"])] += 1
                if r["status"] == "ok":
                    got[r["kind"]] += 1
                    shaok[r["kind"]] += bool(r.get("sha_ok"))
    for k in KINDS:
        print(f"{k:15s} inventory {by[k]:>7,}  reconstructed {got[k]:>7,} ({100*got[k]/max(1,by[k]):5.1f}%)"
              f"  sha-verified {shaok[k]:>7,}")
    print("statuses:", dict(status))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="print coverage and exit")
    ap.add_argument("--limit", type=int, help="reconstruct at most N files (for testing)")
    a = ap.parse_args()
    report() if a.report else run(a.limit)
