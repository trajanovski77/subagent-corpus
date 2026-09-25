#!/usr/bin/env python3
"""Batch files, validation and merging for LLM annotation of the corpus.

    python3 code/llm_labels.py prepare roles [--batch 200]     # unique (name, description) items -> batches
    python3 code/llm_labels.py prepare readme [--batch 40]     # repository README items -> batches
    python3 code/llm_labels.py sample roles reliability 1500   # stratified reliability sample (re-labelled by a second rater)
    python3 code/llm_labels.py validate roles haiku             # which batches are missing or malformed
    python3 code/llm_labels.py merge roles haiku                # -> data/v2/labels/roles_haiku.jsonl.gz
    python3 code/llm_labels.py agreement roles haiku sonnet     # Krippendorff's alpha between two raters
    python3 code/llm_labels.py humankit roles 400               # annotation sheets for two human annotators

Annotation is done by Claude subagents that read a codebook (``annotation/codebook_*.md``) and one batch file and
write one JSON line per item. This module owns everything around that step, so the annotators never see anything
but the codebook and the items, and every label can be traced to its batch, rater and codebook version.

Item identity: ``sha1(name + "\\n" + description)[:16]`` over the stripped strings, so byte-identical
specifications across repositories are labelled once and share the label.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "data" / "v2"
LAB = V2 / "labels"
DESC_CHARS = 700
README_CHARS = 3000

SCHEMAS = {
    "roles": {
        "role": {"REQ", "ARCH", "IMPL", "TEST", "REVIEW", "SEC", "DEBUG", "REFACT", "DOCS", "OPS", "DATA", "UX",
                 "EXPLORE", "PLAN", "NONSE", "UNCLEAR"},
        "mode": {"inspect", "change", "mixed", "unclear"},
        "readonly_claim": {True, False},
        "boilerplate": {True, False},
    },
    "constraints": {
        "polarity": {"prohibit", "require", "other"},
        "restricts_writes": {True, False},
    },
    "readme": {
        "category": {"ENGINEERED", "TEMPLATE_COLLECTION", "TUTORIAL_LEARNING", "PERSONAL_CONFIG", "DEMO_EXPERIMENT",
                     "NON_SOFTWARE", "UNCLEAR"},
        "confidence": {"high", "medium", "low"},
    },
}


CONSTRAINT_TOPICS = {"FS_MODIFY", "EXEC", "VCS", "SCOPE", "SECRETS", "EXTERNAL", "DESTRUCTIVE", "QUALITY", "OUTPUT",
                     "ESCALATE", "HONESTY", "DELEGATION", "OTHER"}


def item_id(name: str, desc: str) -> str:
    return hashlib.sha1((name + "\n" + desc).encode("utf-8", "replace")).hexdigest()[:16]


def text(v) -> str:
    return v.strip() if isinstance(v, str) else ("" if v is None else json.dumps(v, ensure_ascii=False))


def role_items() -> list[dict]:
    seen: dict[str, dict] = {}
    with gzip.open(V2 / "agents.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if not (r.get("available") and r.get("is_spec")):
                continue
            n, d = text(r.get("name")), text(r.get("description"))
            i = item_id(n, d)
            if i not in seen:
                seen[i] = {"id": i, "name": n[:120], "description": (d[:DESC_CHARS] + "…") if len(d) > DESC_CHARS else d,
                           "n_specs": 0, "repos": set()}
            seen[i]["n_specs"] += 1
            seen[i]["repos"].add(r["repo"])
    out = []
    for v in seen.values():
        v["n_repos"] = len(v.pop("repos"))
        out.append(v)
    return sorted(out, key=lambda x: x["id"])


def readme_items() -> list[dict]:
    meta = V2.parent / "repometa_v2.jsonl.gz"
    items = []
    spec_repos = set()
    with gzip.open(V2 / "agents.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("available") and r.get("is_spec"):
                spec_repos.add(r["repo"])
    with gzip.open(meta, "rt") as fh:
        for line in fh:
            m = json.loads(line)
            if m["frame_repo"] not in spec_repos:
                continue
            readme = (m.get("readme") or {}).get("text") or ""
            items.append({
                "id": hashlib.sha1(m["frame_repo"].encode()).hexdigest()[:16],
                "repo": m.get("repo") or m["frame_repo"],
                "description": (m.get("description") or "")[:300],
                "topics": (m.get("topics") or [])[:12],
                "languages": list((m.get("languages") or {}).keys())[:8],
                "stars": m.get("stars"), "commits_to_snapshot": m.get("commits_to_snapshot"),
                "contributors": m.get("contributors"), "created": (m.get("created") or "")[:10],
                "is_template": m.get("is_template"),
                "readme": readme[:README_CHARS] + ("…" if len(readme) > README_CHARS else ""),
            })
    return sorted(items, key=lambda x: x["id"])


def batch_dir(task: str) -> Path:
    return LAB / task / "in"


def out_dir(task: str, rater: str) -> Path:
    return LAB / task / f"out_{rater}"


def prepare(task: str, size: int) -> None:
    items = role_items() if task == "roles" else readme_items()
    d = batch_dir(task)
    d.mkdir(parents=True, exist_ok=True)
    (LAB / task / "items.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))
    keep = {"roles": ("id", "name", "description"),
            "readme": ("id", "repo", "description", "topics", "languages", "stars", "commits_to_snapshot",
                       "contributors", "created", "is_template", "readme")}[task]
    n = 0
    for b in range(0, len(items), size):
        chunk = [{k: i[k] for k in keep} for i in items[b:b + size]]
        (d / f"batch_{b // size:04d}.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunk))
        n += 1
    print(f"{task}: {len(items):,} items in {n} batches of <= {size} under {d.relative_to(ROOT)}")


def sample(task: str, name: str, k: int, seed: int = 20260916) -> None:
    """A reliability sample, stratified by the first rater's role label when available, else simple random."""
    items = [json.loads(l) for l in (LAB / task / "items.jsonl").read_text().splitlines()]
    rng = random.Random(seed)
    chosen = rng.sample(items, min(k, len(items)))
    d = LAB / task / f"in_{name}"
    d.mkdir(parents=True, exist_ok=True)
    keep = ("id", "name", "description") if task == "roles" else tuple(chosen[0].keys())
    rng.shuffle(chosen)
    size = 150 if task == "roles" else 30
    for b in range(0, len(chosen), size):
        chunk = [{kk: c[kk] for kk in keep if kk in c} for c in chosen[b:b + size]]
        (d / f"batch_{b // size:04d}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in chunk))
    print(f"{task}/{name}: {len(chosen):,} items in {(len(chosen) + size - 1) // size} batches under {d.relative_to(ROOT)}")


def validate(task: str, rater: str, indir: str = "in") -> list[str]:
    schema = SCHEMAS[task]
    bad = []
    src = LAB / task / indir
    dst = out_dir(task, rater)
    for bf in sorted(src.glob("batch_*.jsonl")):
        ids = [json.loads(l)["id"] for l in bf.read_text().splitlines() if l.strip()]
        of = dst / bf.name
        if not of.exists():
            bad.append(f"{bf.name}: missing")
            continue
        got, problems = [], []
        for ln, line in enumerate(of.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                problems.append(f"line {ln} not JSON")
                continue
            got.append(o.get("id"))
            for field, allowed in schema.items():
                if o.get(field) not in allowed:
                    problems.append(f"line {ln} {field}={o.get(field)!r}")
            if task == "constraints":
                t = o.get("topics")
                if not (isinstance(t, list) and t and all(x in CONSTRAINT_TOPICS for x in t)):
                    problems.append(f"line {ln} topics={t!r}")
        if got != ids:
            missing = len(set(ids) - set(got))
            extra = len(set(got) - set(ids))
            order = "order differs" if set(got) == set(ids) else ""
            problems.append(f"ids: {missing} missing, {extra} unexpected, {len(got)} lines for {len(ids)} items {order}".strip())
        if problems:
            bad.append(f"{bf.name}: " + "; ".join(problems[:5]))
    print(f"{task}/{rater} ({indir}): {len(list(src.glob('batch_*.jsonl')))} batches, {len(bad)} with problems")
    for b in bad[:40]:
        print("  ", b)
    return bad


def merge(task: str, rater: str, indir: str = "in") -> None:
    """Merge every valid label this rater produced, across all of its output directories."""
    rows = {}
    files = sorted(f for d in (LAB / task).glob(f"out_{rater}*") for f in d.glob("batch_*.jsonl"))
    for of in files:
        for line in of.read_text().splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if all(o.get(f) in allowed for f, allowed in SCHEMAS[task].items()):
                rows.setdefault(o["id"], {**o, "rater": rater, "batch": of.name})
    out = LAB / f"{task}_{rater}.jsonl.gz"
    print(f"read {len(files)} output files")
    with gzip.open(out, "wt") as fh:
        for r in rows.values():
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"merged {len(rows):,} labels into {out.relative_to(ROOT)}")


def missing_items(task: str, rater: str, size: int = 200) -> None:
    """Write mop-up batches for items that no valid label covers yet."""
    items = [json.loads(l) for l in (LAB / task / "items.jsonl").read_text().splitlines()]
    have = set()
    for of in (LAB / task).glob("out_*/batch_*.jsonl"):
        for line in of.read_text().splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if all(o.get(f) in allowed for f, allowed in SCHEMAS[task].items()):
                have.add(o.get("id"))
    todo = [i for i in items if i["id"] not in have]
    d = LAB / task / "in_mopup"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("batch_*.jsonl"):
        f.unlink()
    # A mop-up batch must carry everything the codebook needs to judge the item, exactly as the
    # first-pass batch did; emitting bare ids leaves the annotator nothing to read.
    keep = {"roles": ("id", "name", "description"),
            "constraints": ("id", "sentence", "context"),
            "readme": ("id", "repo", "description", "topics", "languages", "stars",
                       "commits_to_snapshot", "contributors", "created", "is_template", "readme"),
            }[task]
    for b in range(0, len(todo), size):
        chunk = [{k: c[k] for k in keep if k in c} for c in todo[b:b + size]]
        (d / f"batch_{b // size:04d}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in chunk))
    print(f"{len(todo):,} items still unlabelled -> {(len(todo) + size - 1) // size} mop-up batches in {d.relative_to(ROOT)}")


def krippendorff_nominal(pairs: list[tuple[str, str]]) -> float:
    """Krippendorff's alpha for two raters, nominal data, no missing values."""
    coinc = collections.Counter()
    for a, b in pairs:
        coinc[(a, b)] += 1
        coinc[(b, a)] += 1
    n_c = collections.Counter()
    for (a, _), v in coinc.items():
        n_c[a] += v
    n = sum(n_c.values())
    if n <= 1:
        return float("nan")
    d_o = sum(v for (a, b), v in coinc.items() if a != b) / n
    d_e = sum(n_c[a] * n_c[b] for a in n_c for b in n_c if a != b) / (n * (n - 1))
    return 1 - d_o / d_e if d_e else float("nan")


def load_labels(task: str, rater: str) -> dict[str, dict]:
    path = LAB / f"{task}_{rater}.jsonl.gz"
    with gzip.open(path, "rt") as fh:
        return {json.loads(l)["id"]: json.loads(l) for l in fh}


def agreement(task: str, r1: str, r2: str) -> None:
    a, b = load_labels(task, r1), load_labels(task, r2)
    common = sorted(set(a) & set(b))
    print(f"{task}: {len(common):,} items labelled by both {r1} and {r2}")
    out = {"raters": [r1, r2], "n_items": len(common)}
    for field in SCHEMAS[task]:
        pairs = [(str(a[i][field]), str(b[i][field])) for i in common]
        agree = sum(x == y for x, y in pairs) / max(1, len(pairs))
        alpha = krippendorff_nominal(pairs)
        out[field] = alpha
        out[f"{field}_raw"] = agree
        print(f"  {field:<15s} raw agreement {100 * agree:5.1f}%   Krippendorff alpha {alpha:.3f}")
    if task == "roles":
        def insp(lab):
            return "inspect" if lab["mode"] == "inspect" else ("change" if lab["mode"] in ("change", "mixed") else "unclear")
        pairs = [(insp(a[i]), insp(b[i])) for i in common]
        out["mode_binary"] = krippendorff_nominal(pairs)
        print(f"  {'mode (inspect vs change+mixed)':<15s} alpha {out['mode_binary']:.3f}")
    # The manuscript quotes these, so write them where paper_numbers.py can read them.
    path = LAB / task / "agreement.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"  wrote {path.relative_to(ROOT)}")


def humankit(task: str, k: int, seed: int = 20260917) -> None:
    items = [json.loads(l) for l in (LAB / task / "items.jsonl").read_text().splitlines()]
    chosen = random.Random(seed).sample(items, k)
    d = ROOT / "annotation" / f"human_{task}"
    d.mkdir(parents=True, exist_ok=True)
    import csv
    for annot in ("A", "B"):
        with open(d / f"sheet_annotator_{annot}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            if task == "roles":
                w.writerow(["id", "name", "description", "role", "mode", "readonly_claim", "lang", "boilerplate"])
                for c in chosen:
                    w.writerow([c["id"], c["name"], c["description"], "", "", "", "", ""])
            else:
                w.writerow(["id", "repo", "description", "readme", "category", "confidence"])
                for c in chosen:
                    w.writerow([c["id"], c["repo"], c["description"], c["readme"], "", ""])
    print(f"wrote two blank sheets of {k} items to {d.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prepare", "sample", "validate", "merge", "agreement", "humankit", "missing"])
    ap.add_argument("task", choices=["roles", "readme", "constraints"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--batch", type=int)
    ap.add_argument("--indir", default="in")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.task, a.batch or (200 if a.task == "roles" else 40))
    elif a.cmd == "sample":
        sample(a.task, a.args[0], int(a.args[1]))
    elif a.cmd == "validate":
        validate(a.task, a.args[0], a.indir)
    elif a.cmd == "merge":
        merge(a.task, a.args[0], a.indir)
    elif a.cmd == "agreement":
        agreement(a.task, a.args[0], a.args[1])
    elif a.cmd == "missing":
        missing_items(a.task, a.args[0] if a.args else "haiku")
    else:
        humankit(a.task, int(a.args[0]))
