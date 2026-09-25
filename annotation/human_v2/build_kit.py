#!/usr/bin/env python3
"""Build the human-validation kit v2: samples, model-label files and the self-contained coder page.

    python3 annotation/human_v2/build_kit.py

Outputs (all in annotation/human_v2/):
    sample_R.jsonl        200 role items (id, position, name, description) in coding order
    sample_S.jsonl        80 specifications (id, position, repo, path) in coding order
    sample_B.jsonl        60 specifications (id, position, repo, path) in coding order
    sample_P.jsonl        60 repositories (id, position, repo) in coding order
    model_labels_<X>.jsonl  model labels + sampling stratum for part X (never shown to coders); P has Haiku only
    sample_meta.json      seeds, quotas, pool sizes (used by code/human_agreement.py for stratum weights)
    coder.html            the annotation page, built from coder_template.html with the items embedded

Sampling (seed 20260923):
    R: from the roles reliability sample (data/v2/labels/roles/in_reliability) restricted to items that have both a
       Haiku and a Sonnet label, stratified by the Haiku mode: inspect 75, change 75, mixed 30, unclear 20.
    S: from the specifications with a Sonnet reliability label, stratified by the Haiku restriction:
       full 27, partial 27, none 26 (population shares are about 17/17/66 %, so full and partial are over-represented).
    B: from all 749 codebook-B specifications (one dominated withholding per E2 repository), stratified by the Haiku
       shell use: change 15, verify 15, inspect 15, none 15. Sonnet labels exist for the part of the sample that falls in
       its reliability batches. (The Sonnet-coded pool holds only 10 change items, too few for the change contrast.)
    P: from the E1 repositories (the population the README screen splits into E2 and the rest) that have a README
       batch item, stratified by the Haiku category: ENGINEERED 30, TEMPLATE_COLLECTION 8, UNCLEAR 6,
       PERSONAL_CONFIG 5, NON_SOFTWARE 4, DEMO_EXPERIMENT 4, TUTORIAL_LEARNING 3. Codebook P had no second model rater.
The coders see the items in a fixed shuffled order (same for everyone): all R items, then S, then B, then P.
The page shows exactly the text the models saw: for R the (name, description) batch line (descriptions truncated at
700 characters, as in the LLM batches), for S the whole batch .md file.
"""
from __future__ import annotations

import collections
import glob
import gzip
import hashlib
import html
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LAB = ROOT / "data" / "v2" / "labels"
SEED = 20260923
QUOTA_R = {"inspect": 75, "change": 75, "mixed": 30, "unclear": 20}
QUOTA_S = {"full": 27, "partial": 27, "none": 26}
QUOTA_B = {"change": 15, "verify": 15, "inspect": 15, "none": 15}
QUOTA_P = {"ENGINEERED": 30, "TEMPLATE_COLLECTION": 8, "UNCLEAR": 6, "PERSONAL_CONFIG": 5, "NON_SOFTWARE": 4,
           "DEMO_EXPERIMENT": 4, "TUTORIAL_LEARNING": 3}
P_FIELDS = ("repo", "description", "topics", "languages", "stars", "commits_to_snapshot", "contributors", "created",
            "is_template", "readme")
ROLE_KEYS = {"REQ": "q", "ARCH": "a", "IMPL": "i", "TEST": "t", "REVIEW": "r", "SEC": "s", "DEBUG": "d",
             "REFACT": "f", "DOCS": "w", "OPS": "o", "DATA": "b", "UX": "x", "EXPLORE": "e", "PLAN": "p",
             "NONSE": "n", "UNCLEAR": "u"}


def jl(path: Path | str) -> list[dict]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def write_jl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def stratified(pool: dict[str, str], quota: dict[str, int], rng: random.Random) -> list[str]:
    """pool: id -> stratum. Draw quota[s] ids per stratum (sorted ids, so the draw is reproducible), then shuffle."""
    by = collections.defaultdict(list)
    for i, s in sorted(pool.items()):
        by[s].append(i)
    chosen = []
    for s, k in quota.items():
        if len(by[s]) < k:
            raise SystemExit(f"stratum {s}: only {len(by[s])} items, quota {k}")
        chosen += rng.sample(by[s], k)
    rng.shuffle(chosen)
    return chosen


# ---------------------------------------------------------------- codebook -> HTML (tiny markdown subset)
def md_inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<i>\1</i>", s)
    return s


def md_to_html(md: str) -> str:
    out, table, lst = [], [], False
    def flush_table():
        nonlocal table
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|[\s\-:|]+\|", r.strip())]
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            h = "".join(f"<th>{md_inline(c)}</th>" for c in cells[0])
            b = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
            out.append(f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>")
            table = []
    for line in md.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        flush_table()
        if re.match(r"\s*- ", line):
            if not lst:
                out.append("<ul>")
                lst = True
            out.append(f"<li>{md_inline(line.split('- ', 1)[1])}</li>")
            continue
        if lst and line.startswith("  ") and line.strip():
            out[-1] = out[-1][:-5] + " " + md_inline(line.strip()) + "</li>"
            continue
        if lst:
            out.append("</ul>")
            lst = False
        m = re.match(r"(#+)\s+(.*)", line)
        if m:
            lvl = min(4, len(m.group(1)) + 1)
            out.append(f"<h{lvl}>{md_inline(m.group(2))}</h{lvl}>")
        elif line.strip():
            out.append(f"<p>{md_inline(line)}</p>")
    flush_table()
    if lst:
        out.append("</ul>")
    return "\n".join(out)


def section(md: str, start: str, end: str | None) -> str:
    i = md.index(start)
    j = md.index(end, i) if end else len(md)
    return md[i:j]


def main() -> None:
    # ------------------------------------------------------------ R
    haiku = {r["id"]: r for r in jl(LAB / "roles_haiku.jsonl.gz")}
    sonnet = {r["id"]: r for r in jl(LAB / "roles_sonnet.jsonl.gz")}
    rel = {}
    for f in sorted(glob.glob(str(LAB / "roles" / "in_reliability" / "batch_*.jsonl"))):
        for r in jl(f):
            rel[r["id"]] = r
    pool_r = {i: haiku[i]["mode"] for i in rel if i in haiku and i in sonnet}
    rng = random.Random(SEED)
    ids_r = stratified(pool_r, QUOTA_R, rng)
    fields_r = ("role", "mode", "readonly_claim")
    sample_r = [{"id": i, "position": k, "name": rel[i]["name"], "description": rel[i]["description"]}
                for k, i in enumerate(ids_r)]
    models_r = [{"id": i, "stratum": pool_r[i],
                 "haiku": {f: haiku[i][f] for f in fields_r}, "sonnet": {f: sonnet[i][f] for f in fields_r}}
                for i in ids_r]

    # ------------------------------------------------------------ S
    sd = LAB / "specrestr"
    h_s = {}
    for f in sorted(glob.glob(str(sd / "out_haiku*" / "batch_*.jsonl"))):  # out_haiku/ sorts before out_haiku_mopup/
        for r in jl(f):
            h_s[r["id"]] = r                                                  # mop-up re-labels win
    s_s = {}
    for f in sorted(glob.glob(str(sd / "out_sonnet_reliability" / "batch_*.jsonl"))):
        for r in jl(f):
            s_s[r["id"]] = r
    items_s = {r["id"]: r for r in jl(sd / "items.jsonl")}
    texts = {Path(p).stem: Path(p) for p in glob.glob(str(sd / "in*" / "batch_*" / "*.md"))}
    pool_s = {i: h_s[i]["restriction"] for i in s_s if i in h_s and i in texts}
    ids_s = stratified(pool_s, QUOTA_S, random.Random(SEED + 1))
    sample_s = [{"id": i, "position": k, "repo": items_s.get(i, {}).get("repo"), "path": items_s.get(i, {}).get("path")}
                for k, i in enumerate(ids_s)]
    models_s = [{"id": i, "stratum": pool_s[i],
                 "haiku": {k: h_s[i].get(k) for k in ("restriction", "evidence", "where")},
                 "sonnet": {k: s_s[i].get(k) for k in ("restriction", "evidence", "where")}} for i in ids_s]

    # ------------------------------------------------------------ B
    bd = LAB / "shelluse"
    h_b, s_b = {}, {}
    for f in sorted(glob.glob(str(bd / "out_haiku*" / "batch_*.jsonl"))):   # mop-up re-labels win
        for r in jl(f):
            h_b[r["id"]] = r
    for f in sorted(glob.glob(str(bd / "out_sonnet_reliability" / "batch_*.jsonl"))):
        for r in jl(f):
            s_b[r["id"]] = r
    items_b = {r["id"]: r for r in jl(bd / "items.jsonl")}
    texts_b = {Path(p).stem: Path(p) for p in glob.glob(str(bd / "in*" / "batch_*" / "*.md"))}
    pool_b = {i: h_b[i]["shell_use"] for i in h_b if i in texts_b}
    ids_b = stratified(pool_b, QUOTA_B, random.Random(SEED + 2))
    sample_b = [{"id": i, "position": k, "repo": items_b.get(i, {}).get("repo"), "path": items_b.get(i, {}).get("path")}
                for k, i in enumerate(ids_b)]
    pick_b = lambda r: None if r is None else {k: r.get(k) for k in ("shell_use", "evidence")}   # noqa: E731
    models_b = [{"id": i, "stratum": pool_b[i], "haiku": pick_b(h_b[i]), "sonnet": pick_b(s_b.get(i))} for i in ids_b]

    # ------------------------------------------------------------ P
    eng = {r["repo"]: r for r in jl(ROOT / "data" / "v2" / "engineered.jsonl.gz")}
    h_p = {r["id"]: r for r in jl(LAB / "readme_haiku.jsonl.gz")}
    items_p = {}
    for f in sorted(glob.glob(str(LAB / "readme" / "in*" / "batch_*.jsonl"))):
        for r in jl(f):
            items_p[r["id"]] = r
    pool_p = {i: h_p[i]["category"] for i, r in items_p.items()
              if i in h_p and r["repo"] in eng and eng[r["repo"]]["E1"]}
    ids_p = stratified(pool_p, QUOTA_P, random.Random(SEED + 3))
    sample_p = [{"id": i, "position": k, "repo": items_p[i]["repo"]} for k, i in enumerate(ids_p)]
    models_p = [{"id": i, "stratum": pool_p[i], "haiku": {k: h_p[i].get(k) for k in ("category", "confidence")},
                 "sonnet": None} for i in ids_p]

    write_jl(HERE / "sample_R.jsonl", sample_r)
    write_jl(HERE / "sample_S.jsonl", sample_s)
    write_jl(HERE / "model_labels_R.jsonl", models_r)
    write_jl(HERE / "model_labels_S.jsonl", models_s)
    write_jl(HERE / "sample_B.jsonl", sample_b)
    write_jl(HERE / "model_labels_B.jsonl", models_b)
    write_jl(HERE / "sample_P.jsonl", sample_p)
    write_jl(HERE / "model_labels_P.jsonl", models_p)

    # ------------------------------------------------------------ page data (no model labels)
    cb_r = (ROOT / "annotation" / "codebook_roles.md").read_text(encoding="utf-8")
    cb_s = (ROOT / "annotation" / "codebook_spec_restriction.md").read_text(encoding="utf-8")
    cb_b = (ROOT / "annotation" / "codebook_shell_use.md").read_text(encoding="utf-8")
    cb_p = (ROOT / "annotation" / "codebook_repositories.md").read_text(encoding="utf-8")
    roles = []
    for m in re.finditer(r"^\| ([A-Z]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", cb_r, re.M):
        if m.group(1) in ROLE_KEYS:
            roles.append({"code": m.group(1), "label": m.group(2).strip(), "def": m.group(3).strip(),
                          "signals": m.group(4).strip(), "key": ROLE_KEYS[m.group(1)]})
    assert [r["code"] for r in roles] == list(ROLE_KEYS), [r["code"] for r in roles]
    ver_r = re.search(r"Version ([\d.]+)", cb_r).group(1)
    ver_s = re.search(r"Version ([\d.]+)", cb_s).group(1)
    ver_b = re.search(r"Version ([\d.]+)", cb_b).group(1)
    ver_p = re.search(r"Version ([\d.]+)", cb_p).group(1)
    items_page_r = [{"id": x["id"], "name": x["name"], "description": x["description"]} for x in sample_r]
    items_page_s = [{"id": i, "text": texts[i].read_text(encoding="utf-8")} for i in ids_s]
    items_page_b = [{"id": i, "text": texts_b[i].read_text(encoding="utf-8")} for i in ids_b]
    items_page_p = [{"id": i, **{k: items_p[i].get(k) for k in P_FIELDS}} for i in ids_p]
    digest = hashlib.sha256(json.dumps([ids_r, ids_s, ids_b, ids_p]).encode()).hexdigest()[:12]
    data = {
        "kit": "human_v2", "sample_digest": digest, "codebook_R_version": ver_r, "codebook_S_version": ver_s,
        "codebook_B_version": ver_b, "codebook_P_version": ver_p,
        "roles": roles,
        "codebook_R_html": md_to_html(section(cb_r, "## Field 1", "## Field 4")),
        "codebook_S_html": md_to_html(section(cb_s, "## Field 1", "## Field 2")),
        "codebook_B_html": md_to_html(section(cb_b, "## Field 1", "## Field 2")),
        "codebook_P_html": md_to_html(section(cb_p, "## Field 1", "## Field 2")),
        "R": items_page_r, "S": items_page_s, "B": items_page_b, "P": items_page_p,
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\u0021--")
    assert not re.search(r'"(haiku|sonnet|stratum|restriction|mode|role|shell_use|category|confidence)"\s*:', blob), \
        "model labels leaked into page"
    tpl = (HERE / "coder_template.html").read_text(encoding="utf-8")
    assert tpl.count("__KIT_DATA__") == 1
    (HERE / "coder.html").write_text(tpl.replace("__KIT_DATA__", blob), encoding="utf-8")

    meta = {"seed": SEED, "sample_digest": digest,
            "R": {"pool": "roles reliability sample with both Haiku and Sonnet labels", "pool_size": len(pool_r),
                  "pool_by_stratum": dict(collections.Counter(pool_r.values())), "quota": QUOTA_R,
                  "stratum_field": "haiku.mode"},
            "S": {"pool": "specifications with a Sonnet reliability label", "pool_size": len(pool_s),
                  "pool_by_stratum": dict(collections.Counter(pool_s.values())), "quota": QUOTA_S,
                  "stratum_field": "haiku.restriction", "seed": SEED + 1},
            "B": {"pool": "codebook-B specifications (one per E2 repository with a dominated withholding)",
                  "pool_size": len(pool_b), "pool_by_stratum": dict(collections.Counter(pool_b.values())),
                  "quota": QUOTA_B, "stratum_field": "haiku.shell_use", "seed": SEED + 2},
            "P": {"pool": "E1 repositories with a README batch item", "pool_size": len(pool_p),
                  "pool_by_stratum": dict(collections.Counter(pool_p.values())), "quota": QUOTA_P,
                  "stratum_field": "haiku.category", "seed": SEED + 3}}
    (HERE / "sample_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    n_chars = [len(x["text"]) for x in items_page_s]
    n_chars.sort()
    print(f"R: {len(ids_r)} items from a pool of {len(pool_r)}; strata {collections.Counter(pool_r[i] for i in ids_r)}")
    print(f"S: {len(ids_s)} specs from a pool of {len(pool_s)}; strata {collections.Counter(pool_s[i] for i in ids_s)}")
    print(f"B: {len(ids_b)} specs from a pool of {len(pool_b)}; {sum(1 for i in ids_b if i in s_b)} with a Sonnet label")
    print(f"P: {len(ids_p)} repositories from a pool of {len(pool_p)}")
    print(f"S text length (chars): median {n_chars[len(n_chars) // 2]}, total {sum(n_chars):,}")
    print(f"coder.html: {(HERE / 'coder.html').stat().st_size / 1024:.0f} KiB, sample digest {digest}")


if __name__ == "__main__":
    main()
