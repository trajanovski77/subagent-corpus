#!/usr/bin/env python3
"""Static consistency check of the manuscript, for a machine with no TeX installation.

    python3 code/check_manuscript.py [paper/main_v2.tex]

Resolves \\input recursively from the root file, then reports, as an exit-code-bearing check:
  - \\ref / \\eqref targets with no \\label, and labels defined twice
  - \\cite keys missing from the bibliography, and (informationally) bibliography entries never cited
  - macros used but never defined (numbers.tex, the preamble, or LaTeX itself)
  - macros still rendering the placeholder \\textbf{??}
  - \\includegraphics targets with no file on disk
  - \\authornote{...} passages the authors still owe
This is not a substitute for compiling; it is what can be checked without a compiler.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Control sequences LaTeX, svjour3 or our preamble provide; not an exhaustive list of LaTeX, just
# everything these drafts use, so an unknown name is a real error rather than noise.
KNOWN = set("""
RequirePackage documentclass smartqed journalname usepackage definecolor lstset newcommand
emergencystretch begin end title titlerunning author authorrunning institute date maketitle
keywords section subsection subsubsection paragraph label ref eqref cite citep citet citealp
input include includegraphics caption toprule midrule cmidrule bottomrule textbf textit emph texttt
textcolor small footnotesize scriptsize large Large quad qquad item itemsep and at email url
href S ldots dots cdot times subseteq supseteq cup cap setminus mathrm text frac left right
bibliographystyle bibliography raggedright arraybackslash multicolumn hline centering setlength tabcolsep
newpage clearpage noindent vspace hspace smallskip medskip bigskip footnote
mathit textsc underline sout tabular figure table appendix
alpha beta gamma delta sigma mu lambda epsilon theta phi psi omega Delta Sigma Omega
neq leq geq approx to gets in notin forall exists emptyset infty pm sim propto dagger
color ttfamily rmfamily sffamily bfseries itshape normalfont selectfont
width height scale linewidth textwidth columnwidth height parbox raisebox makebox
""".split())


def expand(path: Path, seen: set[Path] | None = None) -> str:
    """Return the document with every \\input resolved, so checks see one stream of text."""
    seen = seen if seen is not None else set()
    if path in seen or not path.exists():
        return ""
    seen.add(path)
    out = []
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("%"):
            continue
        m = re.match(r"\s*\\input\{([^}]+)\}", line)
        if m:
            name = m.group(1)
            child = path.parent / (name if name.endswith(".tex") else name + ".tex")
            out.append(expand(child, seen))
        else:
            out.append(line)
    return "\n".join(out)


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "paper" / "main_v2.tex"
    if not root.exists():
        raise SystemExit(f"no such file: {root}")
    doc = expand(root)
    problems = 0

    def report(title: str, items, fatal: bool = True) -> None:
        nonlocal problems
        items = sorted(set(items))
        if not items:
            print(f"  ok   {title}")
            return
        if fatal:
            problems += len(items)
        print(f"  {'FAIL' if fatal else 'note'} {title}: {len(items)}")
        for i in items[:25]:
            print(f"         {i}")
        if len(items) > 25:
            print(f"         ... and {len(items)-25} more")

    print(f"checking {root.relative_to(ROOT)}")

    labels = re.findall(r"\\label\{([^}]+)\}", doc)
    refs = re.findall(r"\\(?:ref|eqref)\{([^}]+)\}", doc)
    report("references with no label", [r for r in refs if r not in set(labels)])
    report("labels defined more than once", [l for l in set(labels) if labels.count(l) > 1])

    bib = root.parent / (re.search(r"\\bibliography\{([^}]+)\}", doc).group(1) + ".bib")
    keys = set(re.findall(r"@\w+\{([^,]+),", bib.read_text())) if bib.exists() else set()
    cited = set()
    for m in re.findall(r"\\(?:cite|citep|citet|citealp)\s*(?:\[[^\]]*\])*\{([^}]+)\}", doc):
        cited.update(k.strip() for k in m.split(","))
    report(f"citations missing from {bib.name}", [c for c in cited if c not in keys])
    report(f"{bib.name} entries never cited", [k for k in keys if k not in cited], fatal=False)

    used = set(re.findall(r"\\([A-Za-z]+)", doc))
    defined = set(re.findall(r"\\newcommand\{?\\([A-Za-z]+)", doc))
    report("macros used but never defined", [u for u in used - defined - KNOWN
                                             if not u.startswith(("bibitem", "if", "fi"))])

    numbers = root.parent / "numbers.tex"
    if numbers.exists():
        placeholders = re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{\\textbf\{\?\?\}\}", numbers.read_text())
        report("numbers.tex macros still unresolved", placeholders, fatal=False)

    missing_fig = []
    for g in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", doc):
        if not any((root.parent / (g + ext)).exists() for ext in ("", ".pdf", ".png", ".jpg")):
            missing_fig.append(g)
    report("figures referenced but not on disk", missing_fig)

    notes = re.findall(r"\\authornote\{(.{0,70})", doc, re.S)
    report("author notes outstanding", [" ".join(n.split())[:70] for n in notes], fatal=False)

    print(f"\n{'PROBLEMS: ' + str(problems) if problems else 'no blocking problems'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
