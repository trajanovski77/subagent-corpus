#!/usr/bin/env python3
"""Regenerate every journal figure from the v2 data.

    python3 code/figures_v2.py            # all figures that their inputs support
    python3 code/figures_v2.py fig3 fig7  # only these

Inputs are the v2 artefacts only: data/v2/spec_table.jsonl.gz (the join of corpus, resolver oracle, text features
and curation), data/v2/engineered.jsonl.gz, data/v2/drift_first_commits.jsonl and data/experiment/runs_subagent.jsonl.
A figure whose inputs are not on disk yet is skipped with a message rather than drawn from stale data.

Palette: Okabe-Ito subset #0072B2 / #D55E00 / #CC79A7, colourblind-safe; every series is also directly labelled,
so identity is never carried by colour alone and the figures survive greyscale print.
"""
from __future__ import annotations

import collections
import gzip
import json
import pathlib
import statistics as st
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stats  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
V2 = DATA / "v2"
OUT = ROOT / "paper"

BLUE, VERM, PINK = "#0072B2", "#D55E00", "#CC79A7"
INK, MUTED, GRID = "#1a1a1a", "#666666", "#d9d9d9"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9.5,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.edgecolor": "#555555", "axes.linewidth": 0.6,
    "xtick.color": "#555555", "ytick.color": "#555555",
    "text.color": INK, "axes.labelcolor": INK,
    "figure.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})


def jl(path: pathlib.Path):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf")
    plt.close(fig)
    print(f"  wrote paper/{name}.pdf")


def despine(ax, keep=("left", "bottom")) -> None:
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(s in keep)


def bars_with_ci(ax, labels, ests, colours, xlabel):
    """Horizontal bars with bootstrap intervals; every bar is annotated with its value."""
    y = range(len(labels))
    means = [e.mean for e in ests]
    lo = [e.mean - e.lo for e in ests]
    hi = [e.hi - e.mean for e in ests]
    ax.barh(list(y), means, color=colours, height=0.6)
    ax.errorbar(means, list(y), xerr=[lo, hi], fmt="none", ecolor=INK, elinewidth=0.8, capsize=2)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel(xlabel)
    ax.xaxis.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for yi, e in zip(y, ests):
        ax.text(min(e.hi + 0.02, 0.98), yi, f"{100*e.mean:.0f}%", va="center", fontsize=7.5, color=MUTED)
    despine(ax)


# ------------------------------------------------------------------------------------------- data
_TABLE: list[dict] | None = None


def table() -> list[dict]:
    global _TABLE
    if _TABLE is None:
        p = V2 / "spec_table.jsonl.gz"
        if not p.exists():
            raise SystemExit("data/v2/spec_table.jsonl.gz missing; run: python3 code/analysis_v2.py table")
        _TABLE = list(jl(p))
    return _TABLE


def pop(rows: list[dict], population: str) -> list[dict]:
    return rows if population == "ALL" else [r for r in rows if r.get(population)]


def has_roles(rows: list[dict]) -> bool:
    return any(r.get("mode") for r in rows)


# ------------------------------------------------------------------------------------------- figures
def fig_concentration() -> None:
    """How unevenly specifications are distributed over repositories (Lorenz curve)."""
    counts = sorted(collections.Counter(r["repo"] for r in table()).values())
    total = sum(counts)
    cum, run = [], 0
    for c in counts:
        run += c
        cum.append(run / total)
    x = [(i + 1) / len(counts) for i in range(len(counts))]
    gini = 1 - sum((cum[i] + (cum[i - 1] if i else 0)) * (1 / len(counts)) for i in range(len(cum)))
    fig, ax = plt.subplots(figsize=(3.3, 2.6))
    ax.plot([0, 1], [0, 1], color=MUTED, linewidth=0.8, linestyle="--")
    ax.plot(x, cum, color=BLUE, linewidth=1.6)
    ax.set_xlabel("repositories (ordered by team size)")
    ax.set_ylabel("share of specifications")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.text(0.05, 0.86, f"Gini {gini:.2f}", transform=ax.transAxes, fontsize=8, color=INK)
    ax.text(0.40, 0.30, "line of equality", fontsize=7, color=MUTED, rotation=32)
    despine(ax)
    save(fig, "fig1_concentration")


def fig_teamsize() -> None:
    """Team-size distribution, log-binned, with the median marked."""
    counts = list(collections.Counter(r["repo"] for r in table()).values())
    fig, ax = plt.subplots(figsize=(3.3, 2.6))
    bins = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584]
    ax.hist(counts, bins=bins, color=BLUE, edgecolor="white", linewidth=0.4)
    ax.set_xscale("log")
    med = st.median(counts)
    ax.axvline(med, color=VERM, linewidth=1.0)
    ax.text(med * 1.15, ax.get_ylim()[1] * 0.85, f"median {med:.0f}", fontsize=7.5, color=VERM)
    ax.set_xlabel("specifications per repository (log scale)")
    ax.set_ylabel("repositories")
    ax.yaxis.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    despine(ax)
    save(fig, "fig2_teamsize")


def fig_roleprivilege(population: str = "E2") -> None:
    """Write and shell capability by the annotated intended mode."""
    rows = pop(table(), population)
    if not has_roles(rows):
        print("  fig3 skipped: role labels not merged yet")
        return
    modes = [("inspect", "inspect"), ("change", "change"), ("mixed", "mixed")]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.4), sharey=True)
    for ax, (field, title) in zip(axes, [("can_write_files", "can write files"), ("can_shell", "can run a shell")]):
        ests, labels = [], []
        for key, label in modes:
            e = stats.estimate(rows, lambda r, f=field: bool(r.get(f)), lambda r, k=key: r.get("mode") == k)
            if e:
                ests.append(e)
                labels.append(f"{label} (n={e.denominator:,})")
        if not ests:
            continue
        bars_with_ci(ax, labels, ests, [BLUE, VERM, PINK][:len(ests)], title)
        ax.set_xlim(0, 1)
    fig.suptitle(f"effective capability by intended mode ({population})", y=1.02, fontsize=9.5)
    save(fig, "fig3_role_privilege")


def fig_mechanism(population: str = "E2") -> None:
    """The dominated-withholding funnel: withheld writes, then what the shell gives back."""
    rows = [r for r in pop(table(), population) if r.get("grant") == "explicit"]
    if not rows:
        print("  fig4 skipped: no explicit grants in population")
        return
    withheld = [r for r in rows if not r.get("can_write_files")]
    shell = [r for r in withheld if r.get("can_shell")]
    scoped = [r for r in shell if r.get("shell_scoped_only")]
    stages = [("explicit tool lists", len(rows)),
              ("withhold every file-writing tool", len(withheld)),
              ("...but grant a shell", len(shell)),
              ("...with the shell command-scoped", len(scoped))]
    fig, ax = plt.subplots(figsize=(4.6, 2.4))
    y = range(len(stages))
    vals = [n for _, n in stages]
    ax.barh(list(y), vals, color=[BLUE, BLUE, VERM, PINK], height=0.6)
    ax.set_yticks(list(y))
    ax.set_yticklabels([s for s, _ in stages])
    ax.invert_yaxis()
    for yi, (_, n) in zip(y, stages):
        ax.text(n + max(vals) * 0.015, yi, f"{n:,}", va="center", fontsize=7.5, color=MUTED)
    ax.set_xlabel("specifications")
    ax.xaxis.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    despine(ax)
    save(fig, "fig4_mechanism")


def fig_fields(population: str = "E2") -> None:
    """Which frontmatter fields developers actually set."""
    rows = pop(table(), population)
    fields = ["tools", "model", "description", "disallowedTools", "permissionMode", "color",
              "maxTurns", "skills", "hooks", "mcpServers", "memory", "isolation", "background", "effort"]
    present = collections.Counter()
    for r in rows:
        for k in (r.get("fm_keys") or []):
            present[k] += 1
    shown = [(f, present.get(f, 0) / len(rows)) for f in fields if present.get(f, 0)]
    shown.sort(key=lambda t: -t[1])
    fig, ax = plt.subplots(figsize=(3.6, 3.0))
    y = range(len(shown))
    ax.barh(list(y), [v for _, v in shown], color=BLUE, height=0.65)
    ax.set_yticks(list(y))
    ax.set_yticklabels([f for f, _ in shown], fontfamily="monospace", fontsize=7.5)
    ax.invert_yaxis()
    for yi, (_, v) in zip(y, shown):
        ax.text(v + 0.015, yi, f"{100*v:.0f}%", va="center", fontsize=7, color=MUTED)
    ax.set_xlim(0, 1.08)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel(f"share of specifications ({population})")
    ax.xaxis.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    despine(ax)
    save(fig, "fig5_fields")


def fig_defects(population: str = "E2") -> None:
    """The silent-defect census, as repository-weighted prevalences with intervals."""
    rows = pop(table(), population)
    expl = lambda r: r.get("grant") == "explicit"                                     # noqa: E731
    specs = [
        ("names a removed tool", lambda r: (r.get("n_removed_legacy") or 0) > 0, expl),
        ("names a tool that never existed", lambda r: (r.get("n_never_valid") or 0) > 0, expl),
        ("effective tool set is empty", lambda r: bool(r.get("resolves_nothing")), expl),
        ("loses Grep/Glob to the shell", lambda r: bool(r.get("grep_glob_dropped")), expl),
        ("withholds writes, keeps a shell", lambda r: not r.get("can_write_files") and bool(r.get("can_shell")), expl),
    ]
    labels, ests = [], []
    for label, pred, denom in specs:
        e = stats.estimate(rows, pred, denom)
        if e:
            labels.append(label)
            ests.append(e)
    if not ests:
        print("  fig6 skipped: no estimates")
        return
    fig, ax = plt.subplots(figsize=(4.8, 2.4))
    bars_with_ci(ax, labels, ests, [BLUE, BLUE, BLUE, PINK, VERM][:len(ests)],
                 f"repository-weighted share of explicit grants ({population})")
    ax.set_xlim(0, min(1.0, max(e.hi for e in ests) + 0.12))
    save(fig, "fig6_defects")


def fig_heatmap(population: str = "E2") -> None:
    """Tool-by-mode grant rates: what each kind of delegate is actually given."""
    rows = pop(table(), population)
    if not has_roles(rows):
        print("  fig7 skipped: role labels not merged yet")
        return
    tools = ["Read", "Grep", "Glob", "Bash", "Write", "Edit", "NotebookEdit", "Task", "WebFetch", "TodoWrite"]
    modes = ["inspect", "change", "mixed"]
    grid, ns = [], []
    for m in modes:
        sub = [r for r in rows if r.get("mode") == m]
        ns.append(len(sub))
        grid.append([sum(1 for r in sub if t in (r.get("effective") or [])) / len(sub) if sub else 0.0
                     for t in tools])
    fig, ax = plt.subplots(figsize=(6.2, 2.0))
    im = ax.imshow(grid, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(tools)))
    ax.set_xticklabels(tools, rotation=35, ha="right", fontfamily="monospace", fontsize=7.5)
    ax.set_yticks(range(len(modes)))
    ax.set_yticklabels([f"{m} (n={n:,})" for m, n in zip(modes, ns)])
    for i in range(len(modes)):
        for j in range(len(tools)):
            v = grid[i][j]
            ax.text(j, i, f"{100*v:.0f}", ha="center", va="center", fontsize=7,
                    color="white" if v > 0.55 else INK)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("share holding the tool after resolution", fontsize=7.5)
    cb.ax.tick_params(labelsize=7)
    despine(ax, keep=())
    save(fig, "fig7_heatmap")


def fig_cooccurrence(population: str = "E2") -> None:
    """Prose restriction against enforced grant: the two channels, cross-tabulated."""
    rows = pop(table(), population)
    if not any("readonly_claim" in r for r in rows):
        print("  fig8 skipped: text features missing")
        return
    cells = collections.Counter()
    for r in rows:
        claims = bool(r.get("readonly_claim"))
        writes = bool(r.get("can_write_files")) or bool(r.get("can_shell"))
        cells[(claims, writes)] += 1
    grid = [[cells[(True, False)], cells[(True, True)]],
            [cells[(False, False)], cells[(False, True)]]]
    total = sum(sum(row) for row in grid) or 1
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    im = ax.imshow([[v / total for v in row] for row in grid], cmap="Blues", vmin=0, vmax=0.6)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["cannot write\nor shell", "can write\nor shell"], fontsize=7.5)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["prose claims\nread-only", "no such\nclaim"], fontsize=7.5)
    for i in range(2):
        for j in range(2):
            v = grid[i][j]
            ax.text(j, i, f"{v:,}\n{100*v/total:.1f}%", ha="center", va="center", fontsize=7.5,
                    color="white" if v / total > 0.35 else INK)
    ax.set_title(f"prose versus enforcement ({population})", fontsize=9)
    despine(ax, keep=())
    save(fig, "fig8_cooccurrence")


def fig_adoption() -> None:
    """When these files were first committed: the convention's age."""
    p = V2 / "drift_first_commits.jsonl"
    if not p.exists():
        print("  fig9 skipped: drift_first_commits.jsonl missing")
        return
    months = collections.Counter()
    for r in jl(p):
        d = r.get("first_commit") or r.get("date")
        if isinstance(d, str) and len(d) >= 7:
            months[d[:7]] += 1
    if not months:
        print("  fig9 skipped: no dated files")
        return
    keys = sorted(months)
    vals = [months[k] for k in keys]
    fig, ax = plt.subplots(figsize=(4.8, 2.3))
    ax.bar(range(len(keys)), vals, color=BLUE, width=0.8)
    step = max(1, len(keys) // 10)
    ax.set_xticks(range(0, len(keys), step))
    ax.set_xticklabels([keys[i] for i in range(0, len(keys), step)], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("files first committed")
    ax.yaxis.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    despine(ax)
    save(fig, "fig9_adoption")


def fig_experiment() -> None:
    """RQ5: success on forbidden tasks by configuration and model, with Wilson intervals."""
    p = DATA / "experiment" / "runs_subagent.jsonl"
    if not p.exists():
        print("  fig10 skipped: experiment runs missing")
        return
    runs = [r for r in jl(p) if r.get("task") in {"T2", "T3", "T4", "T5"} and r.get("success") is not None]
    if not runs:
        print("  fig10 skipped: no scored forbidden-task runs")
        return
    configs = ["C0", "C1", "C2", "C3", "C4"]
    names = {"C0": "C0 unrestricted", "C1": "C1 prompt only", "C2": "C2 tools only",
             "C3": "C3 tools+prompt", "C4": "C4 no shell"}
    order = {"haiku": 0, "sonnet": 1, "opus": 2}   # smallest to largest model
    models = sorted({r["model"] for r in runs}, key=lambda m: order.get(m, 9))
    colours = {m: c for m, c in zip(models, [BLUE, VERM, PINK])}
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    width = 0.8 / max(1, len(models))
    for mi, m in enumerate(models):
        xs, ys, los, his = [], [], [], []
        for ci, c in enumerate(configs):
            sub = [r for r in runs if r["config"] == c and r["model"] == m]
            if not sub:
                continue
            k = sum(1 for r in sub if r["success"])
            lo, hi = stats.wilson_ci(k, len(sub))
            xs.append(ci + (mi - (len(models) - 1) / 2) * width)
            ys.append(k / len(sub))
            los.append(max(0.0, k / len(sub) - lo))   # Wilson bounds can sit a rounding error inside 0 or 1
            his.append(max(0.0, hi - k / len(sub)))
        ax.bar(xs, ys, width=width * 0.9, color=colours[m], label=m.capitalize())
        ax.errorbar(xs, ys, yerr=[los, his], fmt="none", ecolor=INK, elinewidth=0.7, capsize=1.5)
    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels([names[c] for c in configs], fontsize=7.5)
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("forbidden task completed")
    ax.yaxis.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=len(models), loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=7.5)
    despine(ax)
    save(fig, "fig10_experiment")


def fig_pipeline() -> None:
    """Schematic of the study pipeline: what each stage consumes and produces."""
    stages = [
        ("Discovery", "code search, size-banded\n\\ frame of repositories"),
        ("Reconstruction", "fetch by git blob id,\nverify by hash"),
        ("Corpus", "parse frontmatter,\njoin governance files"),
        ("Oracles", "execute the runtime:\nresolve, admit, drop"),
        ("Annotation", "codebooks, two model\nraters, reliability sample"),
        ("Curation", "screen fixed before outcomes\n-> ALL / E1 / E2 / E3"),
        ("Analysis", "repository-level\nbootstrap, paired tests"),
        ("Experiment", "5 configs x 6 tasks x 3 models;\nreport-only extension"),
    ]
    cols, rows = 4, 2
    bw, bh = 0.225, 0.30                      # box width and height in axis units
    gapx = (1.0 - cols * bw) / (cols - 1)
    fig, ax = plt.subplots(figsize=(6.6, 2.6))
    for i, (title, body) in enumerate(stages):
        r, c = divmod(i, cols)
        x = c * (bw + gapx)
        y = 0.60 - r * 0.42
        colour = VERM if title in ("Oracles", "Experiment") else BLUE
        ax.add_patch(plt.Rectangle((x, y), bw, bh, facecolor=colour, alpha=0.12,
                                   edgecolor=colour, linewidth=0.8))
        ax.text(x + bw / 2, y + bh - 0.075, title, ha="center", va="center",
                fontsize=8.5, color=INK, weight="bold")
        ax.text(x + bw / 2, y + 0.095, body.replace("\\ ", ""), ha="center", va="center",
                fontsize=6.4, color=MUTED, linespacing=1.35)
        if c < cols - 1:                       # arrow to the next box in the row
            ax.annotate("", xy=(x + bw + gapx - 0.004, y + bh / 2), xytext=(x + bw + 0.004, y + bh / 2),
                        arrowprops=dict(arrowstyle="-|>", color=MUTED, linewidth=0.7))
    # wrap from the end of row 1 down to the start of row 2
    ax.annotate("", xy=(bw / 2, 0.60 - 0.42 + bh + 0.035), xytext=(1.0 - bw / 2, 0.60 - 0.035),
                arrowprops=dict(arrowstyle="-|>", color=MUTED, linewidth=0.7,
                                connectionstyle="angle,angleA=-90,angleB=180,rad=8"))
    ax.text(0.5, 0.06, "shaded stages execute the coding tool itself; the rest read the artifact",
            ha="center", fontsize=6.8, color=MUTED, style="italic")
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(0.0, 0.95)
    ax.axis("off")
    save(fig, "fig0_pipeline")


FIGURES = {
    "fig0": fig_pipeline,
    "fig1": fig_concentration, "fig2": fig_teamsize, "fig3": fig_roleprivilege,
    "fig4": fig_mechanism, "fig5": fig_fields, "fig6": fig_defects,
    "fig7": fig_heatmap, "fig8": fig_cooccurrence, "fig9": fig_adoption,
    "fig10": fig_experiment,
}


def main() -> None:
    wanted = sys.argv[1:] or list(FIGURES)
    unknown = [w for w in wanted if w not in FIGURES]
    if unknown:
        raise SystemExit(f"unknown figure(s) {unknown}; known: {', '.join(FIGURES)}")
    for name in wanted:
        print(name)
        FIGURES[name]()


if __name__ == "__main__":
    main()
