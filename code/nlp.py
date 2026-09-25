#!/usr/bin/env python3
"""Natural-language analysis of specification descriptions and bodies.

    python3 code/nlp.py sentences     # stage 1: segmentation, deontic modality, emphasis, persona  -> data/v2/nlp/
    python3 code/nlp.py sample N      # stage 2a: stratified sample of directive sentences for LLM constraint labels
    python3 code/nlp.py classify      # stage 2b: embedding classifier trained on those labels, applied to all
    python3 code/nlp.py topics        # stage 3: BERTopic over descriptions
    python3 code/nlp.py consistency   # stage 4: prose restriction vs enforced grant, per specification

WHY THIS STRUCTURE
------------------
The paper's claim is that developers express restrictions in natural language while leaving the enforced
tool grant open. That needs three measurements the tool grant alone cannot give: which directive sentences a
specification contains (stage 1), what those directives are about (stage 2), and whether the prose restriction
agrees with what the runtime actually grants (stage 4). Stage 3 characterises what the corpus is about.

Stage 1 is a transparent lexicon so that every count can be re-derived by hand. Its categories follow the RFC 2119
key-word levels (MUST / MUST NOT / SHOULD / MAY), the convention practitioners already use in these files, and
English-only lexicon results are reported with the share of non-English text they exclude. Stage 2 uses a
multilingual sentence encoder with a classifier trained on LLM-labelled sentences and validated on held-out
labels, so the semantic categories are learned from meaning rather than from keywords.
"""
from __future__ import annotations

import argparse
import collections
import math
import gzip
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "data" / "v2"
NLP = V2 / "nlp"

# ------------------------------------------------------------------------------ lexicon
PROHIBITION = re.compile(
    r"\b(never|must\s+not|mustn['’]?t|shall\s+not|do\s+not|don['’]?t|does\s+not|doesn['’]?t|should\s+not|"
    r"shouldn['’]?t|cannot|can['’]?t|may\s+not|not\s+allowed|not\s+permitted|forbidden|prohibited|"
    r"under\s+no\s+circumstances|refrain\s+from|avoid|no\s+(?:editing|edits|changes|modifications|writes|writing))\b",
    re.I)
OBLIGATION = re.compile(r"\b(must|always|shall|required\s+to|is\s+required|are\s+required|need\s+to|needs\s+to|"
                        r"have\s+to|has\s+to|ensure|make\s+sure|mandatory)\b", re.I)
RECOMMENDATION = re.compile(r"\b(should|prefer|preferably|recommended|ideally|try\s+to|consider|where\s+possible|"
                            r"when\s+possible|if\s+possible)\b", re.I)
PERMISSION = re.compile(r"\b(may|can|allowed\s+to|feel\s+free|permitted\s+to|you\s+are\s+free\s+to)\b", re.I)
EMPHASIS_CAPS = re.compile(r"\b(NEVER|MUST|ALWAYS|IMPORTANT|CRITICAL|DO NOT|DON'T|REQUIRED|MANDATORY|WARNING|NOTE|ONLY)\b")
PERSONA = re.compile(r"^\s*(you\s+are|you['’]re|act\s+as|as\s+an?\s)", re.I | re.M)
HYPE = re.compile(r"\b(world[- ]class|elite|expert|senior|principal|master|guru|ninja|rockstar|10x|legendary|"
                  r"top[- ]tier|seasoned|veteran|god\s*mode)\b", re.I)
READONLY_PROSE = re.compile(
    r"\b(read[- ]only|readonly|never\s+(?:modify|edit|write|change|create|delete)|"
    r"(?:do|does|must|should|shall)\s*n['’]?o?t\s+(?:modify|edit|write|change|create|delete|touch|alter)|"
    r"no\s+(?:code\s+)?(?:edits|changes|modifications)|without\s+(?:modifying|editing|changing)|"
    r"not\s+(?:make|making)\s+(?:any\s+)?(?:changes|edits)|you\s+(?:do\s+not|don['’]?t)\s+(?:write|edit|modify))\b",
    re.I)
CODE_FENCE = re.compile(r"```.*?```", re.S)
SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def script_of(text: str) -> str:
    """Coarse writing-system tag; lexicon results are computed on Latin-script sentences only."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "none"
    latin = sum(1 for c in letters if ord(c) < 0x250)
    return "latin" if latin / len(letters) > 0.7 else "other"


def modality(sentence: str) -> str | None:
    if PROHIBITION.search(sentence):
        return "prohibition"
    if OBLIGATION.search(sentence):
        return "obligation"
    if RECOMMENDATION.search(sentence):
        return "recommendation"
    if PERMISSION.search(sentence):
        return "permission"
    return None


def sentences_of(body: str) -> list[str]:
    body = CODE_FENCE.sub(" ", body)
    out = []
    for chunk in SPLIT.split(body):
        s = re.sub(r"^[\s>*\-#\d.)\[\]x]+", "", chunk).strip()
        if 12 <= len(s) <= 600:
            out.append(s)
    return out


def text_of(v) -> str:
    return v if isinstance(v, str) else ("" if v is None else json.dumps(v, ensure_ascii=False))


def stage_sentences() -> None:
    NLP.mkdir(parents=True, exist_ok=True)
    seen_bodies: dict[str, dict] = {}
    spec_rows = []
    with gzip.open(V2 / "bodies.jsonl.gz", "rt") as fh, gzip.open(NLP / "directive_sentences.jsonl.gz", "wt") as fs:
        for line in fh:
            r = json.loads(line)
            desc, body = text_of(r.get("description")), text_of(r.get("body"))
            key = hashlib.sha1((desc + "\n\x00\n" + body).encode("utf-8", "replace")).hexdigest()[:16]
            if key not in seen_bodies:
                sents = sentences_of(body)
                counts = collections.Counter()
                latin_sents = 0
                for s in sents:
                    if script_of(s) != "latin":
                        continue
                    latin_sents += 1
                    m = modality(s)
                    if m:
                        counts[m] += 1
                        if m in ("prohibition", "obligation"):
                            sid = hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:16]
                            fs.write(json.dumps({"sid": sid, "text_key": key, "modality": m, "sentence": s}, ensure_ascii=False) + "\n")
                seen_bodies[key] = {
                    "text_key": key, "body_chars": len(body), "n_sentences": len(sents), "n_latin_sentences": latin_sents,
                    "script_body": script_of(body), "script_desc": script_of(desc),
                    **{f"n_{m}": counts[m] for m in ("prohibition", "obligation", "recommendation", "permission")},
                    "caps_emphasis": len(EMPHASIS_CAPS.findall(body)),
                    "bold_markers": body.count("**") // 2, "exclamations": body.count("!"),
                    "persona_opening": bool(PERSONA.search(body[:400])),
                    "hype_terms": len(HYPE.findall(desc + " " + body[:1500])),
                    "readonly_prose_body": bool(READONLY_PROSE.search(body)),
                    "readonly_prose_desc": bool(READONLY_PROSE.search(desc)),
                    "has_examples_block": "<example>" in (desc + body),
                    "proactive_trigger": bool(re.search(r"proactively|MUST BE USED|use immediately", desc, re.I)),
                    "desc_chars": len(desc),
                }
            spec_rows.append({"repo": r["repo"], "path": r["path"], "text_key": key})
    with gzip.open(NLP / "texts.jsonl.gz", "wt") as ft:
        for v in seen_bodies.values():
            ft.write(json.dumps(v) + "\n")
    with gzip.open(NLP / "spec_text_keys.jsonl.gz", "wt") as fk:
        for row in spec_rows:
            fk.write(json.dumps(row) + "\n")
    tot = collections.Counter()
    for v in seen_bodies.values():
        for m in ("prohibition", "obligation", "recommendation", "permission"):
            tot[m] += v[f"n_{m}"]
    print(f"{len(spec_rows):,} specifications, {len(seen_bodies):,} distinct description+body texts")
    print("directive sentences (Latin script):", dict(tot))
    print("texts with Latin-script body:", sum(1 for v in seen_bodies.values() if v["script_body"] == "latin"))


# ---------------------------------------------------------------------- stage 2: sample
CONSTRAINT_CODES = ["FS_MODIFY", "EXEC", "VCS", "SCOPE", "SECRETS", "EXTERNAL", "DESTRUCTIVE", "QUALITY",
                    "OUTPUT", "ESCALATE", "HONESTY", "DELEGATION", "OTHER"]


def stage_sample(n: int, seed: int = 20260916) -> None:
    """Stratified by modality; each distinct sentence at most once."""
    rows, seen = [], set()
    with gzip.open(NLP / "directive_sentences.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r["sid"] in seen:
                continue
            seen.add(r["sid"])
            rows.append(r)
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["modality"]].append(r)
    chosen = []
    for m, xs in by.items():
        chosen += rng.sample(xs, min(len(xs), n // 2))
    rng.shuffle(chosen)
    d = V2 / "labels" / "constraints" / "in"
    d.mkdir(parents=True, exist_ok=True)
    size = 150
    for b in range(0, len(chosen), size):
        chunk = [{"id": c["sid"], "sentence": c["sentence"][:500]} for c in chosen[b:b + size]]
        (d / f"batch_{b // size:04d}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in chunk))
    (V2 / "labels" / "constraints" / "items.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chosen))
    print(f"{len(rows):,} distinct directive sentences; sampled {len(chosen):,} into {(len(chosen) + size - 1) // size} batches")


# ------------------------------------------------------------------- stage 2b: classifier
def stage_classify(seed: int = 20260916) -> None:
    """Train a multi-label classifier on the LLM-labelled sentences and apply it to every directive sentence.

    Labels come from codebook C. Features are multilingual sentence embeddings; the model is one-vs-rest logistic
    regression. Performance is reported on a held-out fifth of the labelled sentences, per topic, so the paper can
    state how much of the constraint analysis rests on the classifier rather than on direct labels.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import precision_recall_fscore_support
    from sklearn.model_selection import train_test_split

    # Train on every rater's batches, not one directory: the bulk rater labelled most of the sample,
    # and reading only out_sonnet silently trains on a fraction of it.
    lab, per_rater = {}, collections.Counter()
    for d in sorted((V2 / "labels" / "constraints").glob("out_*")):
        for f in sorted(d.glob("batch_*.jsonl")):
            for line in f.read_text().splitlines():
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(o.get("topics"), list) and o.get("topics"):
                    lab[o["id"]] = o
                    per_rater[d.name] += 1
    print("  training labels per rater:", dict(per_rater))
    items = {json.loads(l)["sid"]: json.loads(l) for l in
             (V2 / "labels" / "constraints" / "items.jsonl").read_text().splitlines()}
    ids = [i for i in lab if i in items]
    print(f"{len(ids):,} labelled sentences available")
    if len(ids) < 400:
        sys.exit("not enough labelled sentences yet")
    texts = [items[i]["sentence"] for i in ids]
    model = SentenceTransformer(ENCODER)
    X = model.encode(texts, batch_size=128, show_progress_bar=True, normalize_embeddings=True)
    codes = CONSTRAINT_CODES
    Y = np.array([[1 if c in lab[i]["topics"] else 0 for c in codes] for i in ids])
    W = np.array([1 if lab[i].get("restricts_writes") else 0 for i in ids])
    # Three-way split. These categories are rare, and `class_weight="balanced"` with the implicit 0.5
    # threshold over-predicts the minority class badly (precision ~0.2 at recall ~0.7). We therefore
    # choose each category's decision threshold on a validation split and report performance on a test
    # split that played no part in either fitting or thresholding.
    idx = np.arange(len(ids))
    tr_all, te = train_test_split(idx, test_size=0.2, random_state=seed, shuffle=True)
    tr, va = train_test_split(tr_all, test_size=0.25, random_state=seed, shuffle=True)
    MIN_POSITIVES = 12          # below this a per-category estimate is not meaningful

    def fit_one(y: "np.ndarray") -> tuple[object, float, dict]:
        """Fit, pick the threshold that maximises validation F1, score on the untouched test split."""
        m = LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0).fit(X[tr], y[tr])
        pv = m.predict_proba(X[va])[:, 1]
        best_t, best_f1 = 0.5, -1.0
        for t in np.arange(0.05, 0.96, 0.01):
            _, _, f1v, _ = precision_recall_fscore_support(y[va], (pv >= t).astype(int),
                                                           average="binary", zero_division=0)
            if f1v > best_f1:
                best_t, best_f1 = float(t), float(f1v)
        p, r, f1, _ = precision_recall_fscore_support(y[te], (m.predict_proba(X[te])[:, 1] >= best_t).astype(int),
                                                      average="binary", zero_division=0)
        return m, best_t, {"precision": round(float(p), 3), "recall": round(float(r), 3),
                           "f1": round(float(f1), 3), "threshold": round(best_t, 2),
                           "support_train": int(y[tr].sum()), "support_test": int(y[te].sum())}

    report, models, thresholds = {}, {}, {}
    for j, c in enumerate(codes):
        # Need positives in every split, or neither the threshold nor the estimate means anything.
        if min(Y[tr, j].sum(), Y[va, j].sum(), Y[te, j].sum()) < MIN_POSITIVES:
            report[c] = {"support_total": int(Y[:, j].sum()), "estimated": False,
                         "reason": f"fewer than {MIN_POSITIVES} positives in some split"}
            continue
        models[c], thresholds[c], report[c] = fit_one(Y[:, j])
    mw, thresholds["restricts_writes"], report["restricts_writes"] = fit_one(W)
    (NLP / "constraint_classifier_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))

    # apply to every distinct directive sentence
    rows, seen = [], set()
    with gzip.open(NLP / "directive_sentences.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r["sid"] in seen:
                continue
            seen.add(r["sid"])
            rows.append(r)
    print(f"applying to {len(rows):,} distinct directive sentences")
    E = model.encode([r["sentence"] for r in rows], batch_size=256, show_progress_bar=True, normalize_embeddings=True)
    preds = {c: (models[c].predict_proba(E)[:, 1] >= thresholds[c]).astype(int) for c in models}
    pw = (mw.predict_proba(E)[:, 1] >= thresholds["restricts_writes"]).astype(int)
    with gzip.open(NLP / "sentence_topics.jsonl.gz", "wt") as fh:
        for k, r in enumerate(rows):
            fh.write(json.dumps({"sid": r["sid"], "text_key": r["text_key"], "modality": r["modality"],
                                 "topics": [c for c in models if preds[c][k]],
                                 "restricts_writes": bool(pw[k]),
                                 "labelled": r["sid"] in lab}) + "\n")
    print("wrote sentence_topics.jsonl.gz")


# ------------------------------------------------------------- stage 4: prose vs enforcement
def stage_prevalence(seed: int = 20260916, replicates: int = 2000) -> None:
    """Category prevalence among directive sentences, estimated from the annotated sample alone.

        python3 code/nlp.py prevalence

    The classifier of stage 2b is released as an artifact but is not accurate enough to carry a
    prevalence claim (see constraint_classifier_report.json), so the paper reports these categories
    from the labelled sentences directly: no extrapolation, and the uncertainty is the sampling
    uncertainty of a stratified sample rather than an unmeasured model error.

    The sample is stratified by modality with equal allocation, so each stratum is re-weighted by its
    share of the population of distinct directive sentences before the estimates are combined.
    """
    items = {json.loads(l)["sid"]: json.loads(l) for l in
             (V2 / "labels" / "constraints" / "items.jsonl").read_text().splitlines()}
    lab = {}
    for d in sorted((V2 / "labels" / "constraints").glob("out_*")):
        for f in sorted(d.glob("batch_*.jsonl")):
            for line in f.read_text().splitlines():
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(o.get("topics"), list) and o.get("topics") and o["id"] in items:
                    lab[o["id"]] = o

    population = collections.Counter()                       # distinct directive sentences per stratum
    seen = set()
    with gzip.open(NLP / "directive_sentences.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r["sid"] not in seen:
                seen.add(r["sid"])
                population[r["modality"]] += 1
    total = sum(population.values())

    by_stratum = collections.defaultdict(list)
    for sid, o in lab.items():
        by_stratum[items[sid]["modality"]].append(o)
    strata = [s for s in by_stratum if population.get(s)]
    weights = {s: population[s] / total for s in strata}

    rng = random.Random(seed)

    def estimate(hit) -> dict:
        point = sum(weights[s] * (sum(1 for o in by_stratum[s] if hit(o)) / len(by_stratum[s])) for s in strata)
        draws = []
        for _ in range(replicates):
            acc = 0.0
            for s in strata:                                  # resample within stratum
                xs = by_stratum[s]
                acc += weights[s] * (sum(1 for _ in xs if hit(rng.choice(xs))) / len(xs))
            draws.append(acc)
        draws.sort()
        return {"prevalence": round(point, 4),
                "lo": round(draws[int(0.025 * replicates)], 4),
                "hi": round(draws[int(0.975 * replicates)], 4),
                "n_labelled": sum(1 for o in lab.values() if hit(o))}

    out = {"n_sample": len(lab), "n_population": total,
           "strata": {s: {"population": population[s], "sampled": len(by_stratum[s]),
                          "weight": round(weights[s], 4)} for s in strata},
           "categories": {c: estimate(lambda o, c=c: c in o["topics"]) for c in CONSTRAINT_CODES},
           "restricts_writes": estimate(lambda o: bool(o.get("restricts_writes")))}
    (NLP / "constraint_prevalence.json").write_text(json.dumps(out, indent=1))
    print(f"{len(lab):,} labelled sentences; population {total:,} distinct directive sentences")
    for s in strata:
        print(f"  stratum {s:<12s} population {population[s]:>7,}  sampled {len(by_stratum[s]):>4}  weight {weights[s]:.3f}")
    print("\n  category prevalence among directive sentences (stratified, 95% bootstrap)")
    rows = sorted(out["categories"].items(), key=lambda kv: -kv[1]["prevalence"])
    for c, e in rows:
        print(f"    {c:<14s} {100*e['prevalence']:5.1f}%  [{100*e['lo']:4.1f},{100*e['hi']:5.1f}]   {e['n_labelled']:>4} labelled")
    e = out["restricts_writes"]
    print(f"    {'restricts writes':<14s} {100*e['prevalence']:5.1f}%  [{100*e['lo']:4.1f},{100*e['hi']:5.1f}]   {e['n_labelled']:>4} labelled")
    print(f"  wrote {(NLP / 'constraint_prevalence.json').relative_to(ROOT)}")


SPEC = V2 / "labels" / "specrestr"
SPEC_CAP = 40_000          # chars per specification text; longer ones keep head and tail
SPEC_BATCH_CHARS = 250_000


def stage_shellsample(seed: int = 20260924) -> None:
    """Codebook B sample: one randomly drawn *dominated-withholding* specification per engineered repository that
    has one (explicit grant, no file-writing tool, an unscoped shell). Annotated with codebook B
    (annotation/codebook_shell_use.md): what, if anything, the text asks the agent to use its shell for.

        python3 code/nlp.py shellsample
    """
    stage_specsample(seed, pred=lambda r: (r["grant"] == "explicit" and not r["can_write_files"] and r["can_shell"]
                                           and not r["shell_scoped_only"]),
                     outdir=V2 / "labels" / "shelluse")


def stage_specsample(seed: int = 20260923, pred=None, outdir=None) -> None:
    """RQ4 spec-level sample: one randomly drawn specification per engineered (E2) repository.

        python3 code/nlp.py specsample

    Drawing one specification per repository makes the sample mean of any indicator an unbiased estimate of
    the paper's standard statistic, the mean over repositories of the within-repository proportion, with no
    between-repository sampling error (every E2 repository is included). Each specification is written as a
    Markdown file (name, description, body) so that an annotator can page through long bodies; batches hold
    about SPEC_BATCH_CHARS characters and list their files in index.txt. Annotated with codebook S
    (annotation/codebook_spec_restriction.md).
    """
    by_repo = collections.defaultdict(list)
    with gzip.open(V2 / "spec_table.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("E2") and (pred is None or pred(r)):
                by_repo[r["repo"]].append(r["path"])
    rng = random.Random(seed)
    pick = {repo: rng.choice(sorted(paths)) for repo, paths in sorted(by_repo.items())}
    want = {(repo, path) for repo, path in pick.items()}
    texts = {}
    with gzip.open(V2 / "bodies.jsonl.gz", "rt") as fh:
        for line in fh:
            b = json.loads(line)
            if (b["repo"], b["path"]) in want:
                texts[(b["repo"], b["path"])] = b
    items = []
    for repo, path in sorted(pick.items()):
        b = texts.get((repo, path), {})
        body = b.get("body") or ""
        if len(body) > SPEC_CAP:
            body = body[:30_000] + "\n\n[... middle of the body omitted for length ...]\n\n" + body[-10_000:]
        sid = hashlib.sha256(f"{repo}\0{path}".encode()).hexdigest()[:16]
        text = (f"# Subagent specification {sid}\n\n## name\n{text_of(b.get('name'))}\n\n"
                f"## description\n{text_of(b.get('description'))}\n\n## body\n{body}\n")
        items.append({"id": sid, "repo": repo, "path": path, "text": text})
    rng.shuffle(items)
    dest = outdir or SPEC
    out = dest / "in"
    out.mkdir(parents=True, exist_ok=True)
    batch, size, n = [], 0, 0
    def flush():
        nonlocal batch, size, n
        if not batch:
            return
        d = out / f"batch_{n:04d}"
        d.mkdir(exist_ok=True)
        for it in batch:
            (d / f"{it['id']}.md").write_text(it["text"])
        (d / "index.txt").write_text("".join(it["id"] + "\n" for it in batch))
        batch, size, n = [], 0, n + 1
    for it in items:
        if batch and size + len(it["text"]) > SPEC_BATCH_CHARS:
            flush()
        batch.append(it)
        size += len(it["text"])
    flush()
    (dest / "items.jsonl").write_text("".join(json.dumps({k: it[k] for k in ("id", "repo", "path")}) + "\n" for it in items))
    print(f"{len(items):,} specifications (one per E2 repository) in {n} batches under {out.relative_to(ROOT)}")


def stage_specprevalence(seed: int = 20260923, replicates: int = 10_000) -> None:
    """Prose write restriction and its consistency with the enforced grant, from the spec-level sample.

        python3 code/nlp.py specprevalence
    """
    items = {json.loads(l)["id"]: json.loads(l) for l in (SPEC / "items.jsonl").read_text().splitlines()}
    lab = {}
    # Haiku is the primary rater; out_sonnet_reliability is the second rater and must never replace it.
    for d in sorted(SPEC.glob("out_haiku*")):
        for f in sorted(d.glob("batch_*.jsonl")):
            for line in f.read_text().splitlines():
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("restriction") in ("full", "partial", "none"):
                    lab[o["id"]] = o
    spec = {}
    with gzip.open(V2 / "spec_table.jsonl.gz", "rt") as fh:
        for line in fh:
            r = json.loads(line)
            spec[(r["repo"], r["path"])] = r
    rows = []
    for sid, it in items.items():
        if sid not in lab:
            continue
        s = spec[(it["repo"], it["path"])]
        rows.append({"repo": it["repo"], "restriction": lab[sid]["restriction"],
                     "reaches": bool(s.get("can_write_files") or (s.get("can_shell") and not s.get("shell_scoped_only"))),
                     "writes": bool(s.get("can_write_files")), "grant": s.get("grant")})
    print(f"{len(rows):,} of {len(items):,} sampled specifications labelled")
    rng = random.Random(seed)

    def boot(stat):
        vals = sorted(stat([rng.choice(rows) for _ in rows]) for _ in range(replicates))
        return stat(rows), vals[int(0.025 * replicates)], vals[int(0.975 * replicates)]

    def share(pred, cond=lambda r: True):
        def f(xs):
            sub = [r for r in xs if cond(r)]
            return sum(pred(r) for r in sub) / max(1, len(sub))
        return f
    out = {"n_labelled": len(rows), "n_sampled": len(items)}
    for name, f in (
        ("full", share(lambda r: r["restriction"] == "full")),
        ("partial", share(lambda r: r["restriction"] == "partial")),
        ("any", share(lambda r: r["restriction"] != "none")),
        ("full_reaches_fs", share(lambda r: r["reaches"], lambda r: r["restriction"] == "full")),
        ("full_holds_write_tool", share(lambda r: r["writes"], lambda r: r["restriction"] == "full")),
        ("full_implicit_grant", share(lambda r: r["grant"] == "implicit", lambda r: r["restriction"] == "full")),
        # the dominated-withholding pathway: no file-writing tool, but an unscoped shell
        ("full_shell_only", share(lambda r: r["reaches"] and not r["writes"], lambda r: r["restriction"] == "full")),
    ):
        est, lo, hi = boot(f)
        out[name] = {"est": round(est, 4), "lo": round(lo, 4), "hi": round(hi, 4)}
        print(f"  {name:24s} {100*est:5.1f}%  [{100*lo:4.1f}, {100*hi:4.1f}]")
    out["n_full"] = sum(r["restriction"] == "full" for r in rows)
    (SPEC / "prevalence.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"  wrote {(SPEC / 'prevalence.json').relative_to(ROOT)}")


def stage_consistency() -> None:
    """Join prose restrictions to the effective grant of every specification."""
    per_text = collections.defaultdict(lambda: {"restrict_write_sentences": 0, "topics": collections.Counter()})
    if (NLP / "sentence_topics.jsonl.gz").exists():
        with gzip.open(NLP / "sentence_topics.jsonl.gz", "rt") as fh:
            for line in fh:
                r = json.loads(line)
                t = per_text[r["text_key"]]
                t["restrict_write_sentences"] += bool(r["restricts_writes"] and r["modality"] == "prohibition")
                for c in r["topics"]:
                    t["topics"][c] += 1
    texts = {t["text_key"]: t for t in (json.loads(l) for l in gzip.open(NLP / "texts.jsonl.gz", "rt"))}
    out = NLP / "spec_prose.jsonl.gz"
    n = 0
    with gzip.open(out, "wt") as fh:
        for row in (json.loads(l) for l in gzip.open(NLP / "spec_text_keys.jsonl.gz", "rt")):
            k = row["text_key"]
            t = texts.get(k, {})
            p = per_text.get(k, {})
            fh.write(json.dumps({
                "repo": row["repo"], "path": row["path"], "text_key": k,
                "prose_readonly_regex": bool(t.get("readonly_prose_body") or t.get("readonly_prose_desc")),
                "restrict_write_sentences": p.get("restrict_write_sentences", 0),
                "n_prohibition": t.get("n_prohibition", 0), "n_obligation": t.get("n_obligation", 0),
                "n_recommendation": t.get("n_recommendation", 0), "n_permission": t.get("n_permission", 0),
                "caps_emphasis": t.get("caps_emphasis", 0), "persona_opening": t.get("persona_opening"),
                "hype_terms": t.get("hype_terms", 0), "body_chars": t.get("body_chars", 0),
                "script_body": t.get("script_body"),
                "topics": dict(p.get("topics", {})),
            }) + "\n")
            n += 1
    print(f"wrote {n:,} rows to {out.relative_to(ROOT)}")


# --------------------------------------------------------------------------- stage 3: topics
ENCODER = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def npmi_coherence(topic_words: list[list[str]], docs_tokens: list[set[str]], top_n: int = 10) -> list[float]:
    """Mean pairwise normalised PMI of each topic's top words, document co-occurrence (Röder et al. 2015)."""
    n = len(docs_tokens)
    df = collections.Counter()
    for toks in docs_tokens:
        df.update(toks)
    out = []
    for words in topic_words:
        ws = [w for w in words[:top_n] if df[w] > 0]
        vals = []
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                a, b = ws[i], ws[j]
                co = sum(1 for toks in docs_tokens if a in toks and b in toks)
                if co == 0:
                    vals.append(-1.0)
                    continue
                pa, pb, pab = df[a] / n, df[b] / n, co / n
                vals.append(math.log(pab / (pa * pb)) / -math.log(pab) if pab < 1 else 1.0)
        out.append(sum(vals) / len(vals) if vals else float("nan"))
    return out


def stage_topics(min_cluster: int = 80, seed: int = 42) -> None:
    import numpy as np
    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sentence_transformers import SentenceTransformer
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    items = [json.loads(l) for l in (V2 / "labels" / "roles" / "items.jsonl").read_text().splitlines()]
    docs = [(i["name"].replace("-", " ").replace("_", " ") + ". " + i["description"])[:800] for i in items]
    NLP.mkdir(parents=True, exist_ok=True)
    emb_path = NLP / "desc_embeddings.npy"
    if emb_path.exists():
        emb = np.load(emb_path)
    else:
        model = SentenceTransformer(ENCODER)
        emb = model.encode(docs, batch_size=128, show_progress_bar=True, normalize_embeddings=True)
        np.save(emb_path, emb)
    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=seed)
    hdb = HDBSCAN(min_cluster_size=min_cluster, metric="euclidean", cluster_selection_method="eom", prediction_data=True)
    vec = CountVectorizer(stop_words="english", min_df=5, ngram_range=(1, 2), token_pattern=r"(?u)\b[A-Za-z][A-Za-z0-9+#.-]{2,}\b")
    tm = BERTopic(embedding_model=None, umap_model=umap_model, hdbscan_model=hdb, vectorizer_model=vec,
                  calculate_probabilities=False, verbose=True)
    topics, _ = tm.fit_transform(docs, embeddings=emb)
    outliers_before = sum(1 for t in topics if t == -1)
    topics = tm.reduce_outliers(docs, topics, strategy="embeddings", embeddings=emb)
    tm.update_topics(docs, topics=topics, vectorizer_model=vec)
    info = tm.get_topic_info()
    tok = re.compile(r"(?u)\b[a-z][a-z0-9+#.-]{2,}\b")
    docs_tokens = [set(tok.findall(d.lower())) for d in docs]
    topic_words = [[w for w, _ in (tm.get_topic(t) or [])] for t in info["Topic"] if t != -1]
    coh = npmi_coherence(topic_words, docs_tokens)
    rows = []
    k = 0
    for _, rec in info.iterrows():
        t = int(rec["Topic"])
        if t == -1:
            continue
        members = [i for i, x in enumerate(topics) if x == t]
        rows.append({"topic": t, "size_items": len(members),
                     "size_specs": sum(items[i]["n_specs"] for i in members),
                     "words": [w for w, _ in tm.get_topic(t)][:12], "npmi": coh[k],
                     "examples": [items[i]["name"] + " :: " + items[i]["description"][:160] for i in members[:6]]})
        k += 1
    (NLP / "topics.json").write_text(json.dumps({"encoder": ENCODER, "min_cluster_size": min_cluster, "seed": seed,
                                                 "n_items": len(docs), "outliers_before_reduction": outliers_before,
                                                 "topics": rows}, indent=1, ensure_ascii=False))
    with gzip.open(NLP / "item_topics.jsonl.gz", "wt") as fh:
        for it, t in zip(items, topics):
            fh.write(json.dumps({"id": it["id"], "topic": int(t)}) + "\n")
    print(f"{len(rows)} topics; outliers before reduction {outliers_before:,}; mean NPMI {sum(coh)/len(coh):.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["sentences", "sample", "classify", "prevalence", "specsample", "specprevalence", "shellsample", "topics", "consistency"])
    ap.add_argument("n", nargs="?", type=int, default=3000)
    a = ap.parse_args()
    if a.stage == "sentences":
        stage_sentences()
    elif a.stage == "sample":
        stage_sample(a.n)
    elif a.stage == "topics":
        stage_topics()
    elif a.stage == "classify":
        stage_classify()
    elif a.stage == "prevalence":
        stage_prevalence()
    elif a.stage == "specsample":
        stage_specsample()
    elif a.stage == "specprevalence":
        stage_specprevalence()
    elif a.stage == "shellsample":
        stage_shellsample()
    elif a.stage == "consistency":
        stage_consistency()
    else:
        sys.exit(f"stage {a.stage} is implemented in the next step")
