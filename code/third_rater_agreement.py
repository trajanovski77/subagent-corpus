#!/usr/bin/env python3
"""Agreement of a third model rater (Claude Opus) with Haiku and Sonnet on the human-validation sample.

    python3 code/third_rater_agreement.py      # reads data/v2/labels/validation_opus/*/out, writes agreement.json there

This is a MODEL-ONLY check. Opus labels the same 400 items as the human-validation kit (annotation/human_v2), blind,
with the same codebooks and the same texts, through the same labelling agent as the other model raters. It measures
whether a stronger model agrees with the primary rater; it is not, and must not be reported as, human validation.
Fields, strata weights and alpha are those of code/human_agreement.py.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from human_agreement import FIELDS, KIT, PARTS, PART_MODELS, compare, load_models, values  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "data" / "v2" / "labels" / "validation_opus"


def load_opus() -> dict:
    out = {p: {} for p in PARTS}
    for p in PARTS:
        for f in sorted(glob.glob(str(VAL / p / "out" / "batch_*.jsonl"))):
            for line in Path(f).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    out[p][r["id"]] = r
    return out


def main() -> None:
    models, weights, meta = load_models(KIT)
    opus = load_opus()
    expected = {p: {json.loads(l)["id"] for l in (KIT / f"sample_{p}.jsonl").read_text().splitlines() if l.strip()}
                for p in PARTS}
    coverage = {p: {"labelled": len(set(opus[p]) & expected[p]), "items": len(expected[p]),
                    "missing": sorted(expected[p] - set(opus[p]))} for p in PARTS}
    res = {}
    for field, (part, _) in FIELDS.items():
        w = weights[part]
        ov = values(opus, field)
        rows = [{"a": "opus", "b": m, **compare(ov, values(models[m], field), w)} for m in PART_MODELS[part]]
        if "sonnet" in PART_MODELS[part]:
            rows.append({"a": "haiku", "b": "sonnet", **compare(values(models["haiku"], field), values(models["sonnet"], field), w)})
        res[field] = rows
    doc = {"what": "third MODEL rater (Claude Opus via the spec-labeler agent), NOT human validation",
           "sample_digest": meta["sample_digest"], "coverage": coverage, "fields": res,
           "note": "alpha = Krippendorff nominal; raw_weighted re-weights items to the pool each part was drawn from"}
    (VAL / "agreement.json").write_text(json.dumps(doc, indent=1, allow_nan=True) + "\n")
    for p, c in coverage.items():
        print(f"part {p}: {c['labelled']}/{c['items']} labelled" + (f", missing {c['missing']}" if c["missing"] else ""))
    print()
    for field, rows in res.items():
        print(field)
        for r in rows:
            a = "  nan" if r["alpha"] != r["alpha"] else f"{r['alpha']:5.2f}"
            print(f"  {r['a']:>6s} vs {r['b']:<7s} n={r['n']:4d}  alpha={a}  raw={r['raw']:.2f}  raw_w={r['raw_weighted']:.2f}")
    print(f"\nwrote {VAL / 'agreement.json'}")


if __name__ == "__main__":
    main()
