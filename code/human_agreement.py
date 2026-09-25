#!/usr/bin/env python3
"""Agreement between human coders and the LLM annotators on the human-validation kit v2.

    python3 code/human_agreement.py              # reads annotation/human_v2/human_*.json, writes agreement.json
    python3 code/human_agreement.py --selftest   # fabricates two coder files from the model labels, runs end to end

Inputs: the files exported by annotation/human_v2/coder.html (``human_<initials>.json``, two or more), and the model
labels of the same sample (``model_labels_{R,S,B,P}.jsonl``, written by build_kit.py). Part P has Haiku labels only,
and only 5 of the 60 part-B items have a Sonnet label, so their Sonnet rows have small or zero n.

For each field it reports Krippendorff's alpha (nominal, two raters; ``krippendorff_nominal`` from llm_labels.py),
raw agreement and n for
    - every pair of human coders,
    - every human vs Haiku and vs Sonnet,
    - the human consensus vs Haiku and vs Sonnet (consensus = the label a strict majority of the coders who labelled
      the item gave; with two coders, the items on which both agree),
    - Haiku vs Sonnet on the same items (reference: the LLM-LLM figure on this sample).
Fields: R role, mode, mode_binary (inspect vs change+mixed, unclear kept as its own value exactly as in
llm_labels.agreement, so the numbers are comparable), readonly_claim; S restriction, restriction_binary (full vs not);
B shell_use, shell_change (change vs not); P category, engineered (ENGINEERED vs not, the E2 decision).

The samples are stratified by the Haiku label (R mode, S restriction, B shell use, P category), so alpha and raw agreement describe
the sample. ``raw_weighted`` re-weights each item by (pool size of its stratum / items drawn from it), which
estimates raw agreement in the pool the sample was drawn from (the reliability pools, see sample_meta.json).
Items a coder left blank are dropped pairwise.
"""
from __future__ import annotations

import argparse
import collections
import glob
import itertools
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "annotation" / "human_v2"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_labels import krippendorff_nominal  # noqa: E402

MODELS = ("haiku", "sonnet")
PARTS = ("R", "S", "B", "P")
PART_MODELS = {"R": MODELS, "S": MODELS, "B": MODELS, "P": ("haiku",)}


def _insp(mode):
    return None if mode is None else ("inspect" if mode == "inspect" else ("change" if mode in ("change", "mixed") else "unclear"))


FIELDS = {  # field -> (part, extractor from a label dict)
    "role": ("R", lambda x: x.get("role")),
    "mode": ("R", lambda x: x.get("mode")),
    "mode_binary": ("R", lambda x: _insp(x.get("mode"))),
    "readonly_claim": ("R", lambda x: None if x.get("readonly_claim") is None else str(bool(x["readonly_claim"])).lower()),
    "restriction": ("S", lambda x: x.get("restriction")),
    "restriction_binary": ("S", lambda x: None if x.get("restriction") is None else ("full" if x["restriction"] == "full" else "not_full")),
    "shell_use": ("B", lambda x: x.get("shell_use")),
    "shell_change": ("B", lambda x: None if x.get("shell_use") is None else ("change" if x["shell_use"] == "change" else "no_change")),
    "category": ("P", lambda x: x.get("category")),
    "engineered": ("P", lambda x: None if x.get("category") is None else ("engineered" if x["category"] == "ENGINEERED" else "not_engineered")),
}
DONE = {"R": lambda x: x.get("role") and x.get("mode") and x.get("readonly_claim") is not None,
        "S": lambda x: x.get("restriction"), "B": lambda x: x.get("shell_use"), "P": lambda x: x.get("category")}


def read_jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_models(kit: Path):
    models = {m: {p: {} for p in PARTS} for m in MODELS}
    strata = {p: {} for p in PARTS}
    for part in PARTS:
        for r in read_jl(kit / f"model_labels_{part}.jsonl"):
            strata[part][r["id"]] = r["stratum"]
            for m in MODELS:
                if r.get(m) is not None:
                    models[m][part][r["id"]] = r[m]
    meta = json.loads((kit / "sample_meta.json").read_text())
    weights = {}
    for part in PARTS:
        pool, quota = meta[part]["pool_by_stratum"], meta[part]["quota"]
        weights[part] = {i: pool[s] / quota[s] for i, s in strata[part].items()}
    return models, weights, meta


def load_humans(files: list[Path], meta: dict) -> dict[str, dict]:
    humans = {}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("sample_digest") != meta["sample_digest"]:
            raise SystemExit(f"{f.name}: sample digest {d.get('sample_digest')} != kit {meta['sample_digest']}")
        name = d.get("initials") or f.stem.replace("human_", "")
        if name in humans:
            name = f.stem
        humans[name] = {**{p: d["labels"].get(p, {}) for p in PARTS}, "_file": f.name,
                        "_n_coded": d.get("n_coded"), "_n_items": d.get("n_items")}
    return humans


def values(rater: dict, field: str) -> dict[str, str]:
    part, get = FIELDS[field]
    out = {}
    for i, lab in rater[part].items():
        v = get(lab) if isinstance(lab, dict) else None
        if v is not None:
            out[i] = v
    return out


def consensus(humans: dict, field: str) -> dict[str, str]:
    per = collections.defaultdict(list)
    for h in humans.values():
        for i, v in values(h, field).items():
            per[i].append(v)
    out = {}
    for i, vs in per.items():
        if len(vs) < 2:
            continue
        v, c = collections.Counter(vs).most_common(1)[0]
        if c * 2 > len(vs):
            out[i] = v
    return out


def compare(a: dict[str, str], b: dict[str, str], w: dict[str, float]) -> dict:
    common = sorted(set(a) & set(b))
    pairs = [(a[i], b[i]) for i in common]
    n = len(pairs)
    raw = sum(x == y for x, y in pairs) / n if n else float("nan")
    wsum = sum(w.get(i, 1.0) for i in common)
    raw_w = sum(w.get(i, 1.0) for i in common if a[i] == b[i]) / wsum if wsum else float("nan")
    alpha = krippendorff_nominal(pairs) if n else float("nan")
    return {"n": n, "alpha": alpha, "raw": raw, "raw_weighted": raw_w}


def compute(humans: dict, models: dict, weights: dict) -> dict:
    names = sorted(humans)
    res = {}
    for field, (part, _) in FIELDS.items():
        w = weights[part]
        pm = PART_MODELS[part]
        mv = {m: values(models[m], field) for m in pm}
        hv = {h: values(humans[h], field) for h in names}
        rows = []
        for h1, h2 in itertools.combinations(names, 2):
            rows.append({"comparison": "human-human", "a": h1, "b": h2, **compare(hv[h1], hv[h2], w)})
        for h in names:
            for m in pm:
                rows.append({"comparison": f"human-{m}", "a": h, "b": m, **compare(hv[h], mv[m], w)})
        cons = consensus(humans, field)
        n_any = len(set().union(*[set(hv[h]) for h in names])) if names else 0
        for m in pm:
            rows.append({"comparison": f"consensus-{m}", "a": "consensus", "b": m, "coverage": len(cons) / n_any if n_any else float("nan"),
                         **compare(cons, mv[m], w)})
        if "sonnet" in pm:
            rows.append({"comparison": "haiku-sonnet", "a": "haiku", "b": "sonnet",
                         **compare(mv["haiku"], mv["sonnet"], w)})
        res[field] = rows
    return res


def coder_stats(humans: dict) -> dict:
    out = {}
    for h, d in humans.items():
        s = {}
        for part, done in DONE.items():
            labs = [x for x in d[part].values() if isinstance(x, dict)]
            ms = sorted(x.get("ms") or 0 for x in labs if done(x))
            s[part] = {"coded": sum(1 for x in labs if done(x)), "unsure": sum(1 for x in labs if x.get("unsure")),
                       "median_s_per_item": round(ms[len(ms) // 2] / 1000, 1) if ms else None,
                       "total_min": round(sum(x.get("ms") or 0 for x in labs) / 60000, 1)}
        out[h] = {"file": d["_file"], **s}
    return out


def fmt(x: float) -> str:
    return "  nan" if x != x else f"{x:5.2f}"


def print_table(res: dict, stats: dict) -> None:
    for h, s in stats.items():
        print(f"coder {h} ({s['file']}): " + " | ".join(
            f"{p} {s[p]['coded']} coded, {s[p]['unsure']} unsure, median {s[p]['median_s_per_item']} s/item, {s[p]['total_min']} min"
            for p in PARTS))
    print()
    for field, rows in res.items():
        print(f"{field}")
        print(f"  {'comparison':<34s}{'n':>5s} {'alpha':>6s} {'raw':>6s} {'raw_w':>6s}")
        for r in rows:
            lab = f"{r['a']} vs {r['b']}"
            if r["comparison"].startswith("consensus"):
                lab += f" (cov {100 * r['coverage']:.0f}%)"
            print(f"  {lab:<34s}{r['n']:5d} {fmt(r['alpha']):>6s} {fmt(r['raw']):>6s} {fmt(r['raw_weighted']):>6s}")
        print()


def run(kit: Path, files: list[Path], out: Path) -> dict:
    models, weights, meta = load_models(kit)
    if len(files) < 2:
        raise SystemExit(f"need at least two human_*.json files in {kit}, found {len(files)}")
    humans = load_humans(files, meta)
    res = compute(humans, models, weights)
    stats = coder_stats(humans)
    doc = {"kit": "human_v2", "sample_digest": meta["sample_digest"], "coders": stats,
           "note": "alpha = Krippendorff nominal (two raters); raw_weighted re-weights items to the reliability pool "
                   "(strata = Haiku mode for R, restriction for S, shell use for B, category for P); "
                   "consensus = strict majority of coders; P has no Sonnet labels",
           "fields": res}
    out.write_text(json.dumps(doc, indent=1, allow_nan=True) + "\n")
    print_table(res, stats)
    print(f"wrote {out}")
    return doc


# ---------------------------------------------------------------- self-test
ROLES = ["REQ", "ARCH", "IMPL", "TEST", "REVIEW", "SEC", "DEBUG", "REFACT", "DOCS", "OPS", "DATA", "UX", "EXPLORE",
         "PLAN", "NONSE", "UNCLEAR"]


def fabricate(kit: Path, dest: Path, initials: str, model: str, noise: float, seed: int) -> Path:
    rng = random.Random(seed)
    meta = json.loads((kit / "sample_meta.json").read_text())
    labs = {p: {} for p in PARTS}
    for r in read_jl(kit / "model_labels_R.jsonl"):
        m = r[model]
        role = m["role"] if rng.random() > noise else rng.choice(ROLES)
        mode = m["mode"] if rng.random() > noise else rng.choice(["inspect", "change", "mixed", "unclear"])
        ro = m["readonly_claim"] if rng.random() > noise else not m["readonly_claim"]
        labs["R"][r["id"]] = {"role": role, "mode": mode, "readonly_claim": ro, "unsure": rng.random() < .05,
                              "t_first": None, "t_last": None, "ms": rng.randint(3000, 20000)}
    for r in read_jl(kit / "model_labels_S.jsonl"):
        v = r[model]["restriction"] if rng.random() > noise else rng.choice(["full", "partial", "none"])
        labs["S"][r["id"]] = {"restriction": v, "evidence": "", "unsure": False, "t_first": None, "t_last": None,
                              "ms": rng.randint(10000, 90000)}
    for r in read_jl(kit / "model_labels_B.jsonl"):
        src = r[model] or r["haiku"]
        v = src["shell_use"] if rng.random() > noise else rng.choice(["change", "verify", "inspect", "none"])
        labs["B"][r["id"]] = {"shell_use": v, "evidence": "", "unsure": False, "t_first": None, "t_last": None,
                              "ms": rng.randint(10000, 90000)}
    for r in read_jl(kit / "model_labels_P.jsonl"):
        v = r["haiku"]["category"] if rng.random() > noise else rng.choice(["ENGINEERED", "TEMPLATE_COLLECTION", "UNCLEAR"])
        labs["P"][r["id"]] = {"category": v, "unsure": False, "t_first": None, "t_last": None, "ms": rng.randint(10000, 60000)}
    labs["R"].pop(next(iter(labs["R"])))  # one blank item, to exercise pairwise dropping
    doc = {"kit": "human_v2", "sample_digest": meta["sample_digest"], "initials": initials, "labels": labs,
           "n_coded": {p: len(labs[p]) for p in PARTS}}
    p = dest / f"human_{initials}.json"
    p.write_text(json.dumps(doc))
    return p


def selftest(kit: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="human_v2_selftest_"))
    try:
        files = [fabricate(kit, tmp, "STA", "haiku", 0.10, 1), fabricate(kit, tmp, "STB", "sonnet", 0.10, 2)]
        doc = run(kit, files, tmp / "agreement.json")
        f = doc["fields"]
        get = lambda field, a, b: next(r for r in f[field] if r["a"] == a and r["b"] == b)
        assert get("role", "STA", "STB")["n"] == 199, get("role", "STA", "STB")
        assert get("restriction", "STA", "STB")["n"] == 80
        assert get("shell_use", "STA", "STB")["n"] == 60
        assert get("category", "STA", "STB")["n"] == 60
        assert get("category", "STA", "haiku")["alpha"] > 0.7
        assert not any(r["b"] == "sonnet" for r in f["category"]), "part P has no Sonnet labels"
        assert get("mode", "STA", "haiku")["alpha"] > 0.7, "coder built from Haiku must agree with Haiku"
        assert get("mode", "STB", "sonnet")["alpha"] > 0.7, "coder built from Sonnet must agree with Sonnet"
        for rows in f.values():
            for r in rows:
                assert r["alpha"] != r["alpha"] or -1.0 <= r["alpha"] <= 1.0, r
                assert r["n"] > 0 or r["b"] == "sonnet", r   # few part-B items have a Sonnet label
        assert json.loads((tmp / "agreement.json").read_text())["sample_digest"] == doc["sample_digest"]
        print("selftest OK (fabricated files and their agreement.json deleted)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=KIT, help="folder with human_*.json (default annotation/human_v2)")
    ap.add_argument("--out", type=Path, default=None, help="output JSON (default <dir>/agreement.json)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(KIT)
    else:
        run(KIT, sorted(Path(p) for p in glob.glob(str(a.dir / "human_*.json"))), a.out or a.dir / "agreement.json")
