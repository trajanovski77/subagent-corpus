# subagent-corpus

Corpus, executable oracles, analysis and linter for

> **Specifying the Machine Team: An Empirical Study of Subagent Definitions in Agentic Software
> Development** — Stefan Trajanovski, Marko Petrov, Ema Pandilova, Ivan Chorbev, Dejan Gjorgjevikj
> (manuscript under review).

Agentic coding tools let a developer define *subagents*: named delegates with their own
instructions, an explicit list of the tools they may use, a model, and a level of autonomy. A subagent
definition is therefore not a prompt but a specification of a machine teammate, and a repository's
agent directory is a small organisational chart for non-human labour, checked into version control.

This repository holds **50,011 such specifications from 3,008 public GitHub repositories**
(snapshot of 27–28 August 2026), the code that collected them, the oracles that make the tool grade
its own specifications, the analysis behind every number in the paper, and a linter that prints the
warnings the tool does not.

## The finding

Developers discriminate by role. An agent whose declared job is to inspect can write files far less
often than one whose job is to change things: a paired difference of **+30.7 percentage points**
(95% CI 27.9 to 33.6) across the 924 repositories that define both kinds of role.

The discrimination stops short of the outcome that matters. The same inspection agents are handed an
unrestricted shell, which returns the capability just withheld. Of the inspection agents that withhold
file-writing tools, **66% are granted unrestricted `Bash`**, only 2% narrow that grant to particular
commands, and just **20% are genuinely read-only**. No role class falls below 84% able to write or
execute. The mechanism is confirmed by execution: an agent holding a shell but no file-editing tool
modifies a file on request.

## Layout

| Path | Contents |
|---|---|
| [`paper/`](paper/) | `main.tex` (Springer `svjour3` class, the package linked from the journal's submission page; files included), `refs.bib`, the nine vector figures, and `build.sh` to compile the PDF |
| [`data/`](data/) | the corpus, gzipped JSON Lines (28 MB), the per-band query log and provenance manifest, with its own [README](data/README.md) describing every file and field |
| [`code/`](code/) | `collect.py` (discovery + exhaustive per-repository inventory), `parsing.py` (the one place a raw file becomes a record), `roles.py` (role instruments), `stats.py` (repository-level bootstrap, ICC), `analyze.py` (every number in the paper), `figures.py`, `oracles.py` (O1 acceptance oracle), `repometa.py`, `lint.py` |
| [`METHOD.md`](METHOD.md) | how the corpus was collected, and the biases the sampling design carries |

## Reproduce the paper's numbers

```bash
pip install -r requirements.txt     # pyyaml (analysis), matplotlib (figures only)
python3 code/analyze.py             # ~90 s; prints every number the paper quotes
python3 code/figures.py             # regenerates the nine figures into paper/
cd paper && ./build.sh              # builds main.pdf (pdflatex/latexmk, or tectonic)
```

`analyze.py` prints the results in the order the paper presents them; its saved output is
[`data/results_final.txt`](data/results_final.txt). Bootstrap seeds are fixed, so the output is
byte-for-byte reproducible.

## Lint an agent directory

```bash
python3 code/lint.py path/to/.claude/agents
```

Reports, per file: specifications the tool will silently ignore (`D1`), tool names the pinned
release does not recognise (`D2a` removed legacy names, `D2b` never-valid names), lists that resolve
to nothing (`D3`), an inert `permissionMode` (`D4`), unknown `model` values (`D5`), duplicate names
of which only one loads (`D6`), fields the tool never reads such as `allowed-tools` (`N1`), and the
paper's central finding as a rule (`P1`): a specification that withholds `Write`/`Edit` but grants
an unscoped shell. It reuses `parsing.py` and `data/tool_vocab.json`, so it cannot disagree with
the analysis, and exits non-zero on error-level findings so it can run in CI.

## Re-collect or re-probe

```bash
gh auth login                       # once
python3 code/collect.py             # three resumable stages; outputs land in data/
python3 code/repometa.py            # repository metadata via the GitHub API
python3 code/oracles.py             # O1 probe; needs the Claude Code CLI on PATH
```

Runtime is dominated by API rate limits, so a full collection takes a few hours. Numbers will not
reproduce exactly on a later run because the population keeps growing; the snapshot behind the paper
is the one archived in `data/`.

## Three things to know before reusing this

**Omitting `tools:` is the most permissive choice, not a neutral default.** It inherits the full
tool pool. An analysis that measures capability only among specifications declaring an explicit list
conditions on a post-treatment variable and understates privilege for exactly the roles that omit
most often.

**Repositories are the unit of analysis.** Specifications within a repository are strongly dependent
(ICC 0.41, design effect 6.34). Pooling 50,011 specifications and applying a binomial interval
understates uncertainty roughly six-fold. `code/stats.py` is the only place this is implemented.

**The role instrument is deliberately low-recall.** A keyword codebook over names and descriptions
scores about 65%, and non-differential misclassification pulls group rates toward the corpus mean,
which manufactures a finding of "role does not matter". The headline contrast therefore uses
`strict_role`, which fires only on an unambiguous token in the `name` field and returns nothing on
ambiguity.

## Oracles

Defect labels come from executing the tool rather than from reading its documentation. Three checks
run with no model inference, no credential, and under a second per subject: whether a specification
is actually loaded (O1), whether the tools it names resolve (O2; output in `data/tool_vocab.json`),
and what the settings layer reports (O3). Their limits, including two claims we drew from the
documentation and withdrew once direct execution refuted them, are set out in `METHOD.md` and in
Section 4.3 of the paper.

## Provenance

All tool behaviour reported here was observed on Claude Code v2.1.233, commit `f8d57569aaf3`. The
tool vocabulary changes between releases, so defect rates are version-conditional. The corpus is a
convenience sample of public repositories and supports no population estimate.

## Citing

See [`CITATION.cff`](CITATION.cff). Until the paper appears:

```bibtex
@unpublished{trajanovski2026machineteam,
  author = {Trajanovski, Stefan and Petrov, Marko and Pandilova, Ema and Chorbev, Ivan and
            Gjorgjevikj, Dejan},
  title  = {Specifying the Machine Team: An Empirical Study of Subagent Definitions
            in Agentic Software Development},
  year   = {2026},
  note   = {Manuscript under review. Corpus and code: \url{https://github.com/trajanovski77/subagent-corpus}},
}
```

## Licence

Code is released under the [MIT licence](LICENSE); the corpus under
[CC BY 4.0](data/LICENSE). `paper/svjour3.cls`, `paper/svglov3.clo` and `paper/spbasic.bst` are
Springer's SVJour3 macro package (© Springer), included so the folder compiles as-is.
