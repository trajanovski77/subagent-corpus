# subagent-corpus

Corpus, executable oracles, annotation, analysis, execution experiment and linter for

> **Specifying the Machine Team: An Empirical Study of Subagent Definitions in Agentic Software
> Development** — Stefan Trajanovski, Marko Petrov, Ema Pandilova, Ivan Chorbev, Dejan Gjorgjevikj
> (manuscript under review).

Agentic coding tools let a developer define *subagents*: named delegates with their own
instructions, an explicit list of the tools they may use, a model, and a level of autonomy. A subagent
definition is therefore not a prompt but a specification of a machine teammate, and a repository's
agent directory is a small organisational chart for non-human labour, checked into version control.

This repository holds **69,316 such specifications from 4,128 public GitHub repositories**
(snapshot of 27–28 August 2026), reconstructed *by git blob identifier and verified by hash* so the
corpus is the snapshot rather than a later state of those paths. It also holds the code that collected
them, the oracles that make the tool grade its own specifications, the annotation codebooks and label
sets, the execution experiment, the analysis behind every number in the paper, and a linter that
prints the warnings the tool does not.

## The finding

Developers discriminate by role, deliberately, in a setting where nothing compels it. Paired within
repository, specifications whose intended mode is to **inspect** hold file-writing tools **31.2
percentage points** less often (95% CI 28.9–33.4) than specifications whose mode is to **change**
things — 43.0 points among those that declare an explicit tool list.

The discrimination stops at the wrong boundary. Ask instead whether the agent can reach the file
system *at all* — by a file-writing tool **or** by a shell — and the gap collapses to **8.3 points**.
Of the explicit grants that withhold every file-writing tool, **68.6% keep an unscoped shell** and
only 1.0% scope it to particular commands.

Execution confirms the mechanism rather than inferring it. Across independent runs of three models,
an agent with the modal inspection grant (`Read`, `Grep`, `Glob`, `Bash`, no file tools, no prompt
restriction) completed the forbidden file change in **99.2%** of runs; with the shell withheld as
well, in **0.0%**.

## Layout

| Path | Contents |
|---|---|
| [`paper/`](paper/) | `main_v2.tex` (Springer `svjour3`), the section drafts it includes, `refs_v2.bib`, `numbers.tex` (generated — no number is typed by hand), and the vector figures |
| [`data/v2/`](data/v2/) | the corpus, oracle output, NLP features, annotation labels and the joined `spec_table.jsonl.gz`, with its own [README](data/README.md) |
| [`annotation/`](annotation/) | the engineered-project protocol (fixed before outcomes were joined) and the six codebooks (R roles, P READMEs, C constraints, S spec restriction, B shell use, K completion claims), plus the two-coder human validation kit (`human_v2/`) |
| [`code/`](code/) | see below |
| [`METHOD.md`](METHOD.md) | how the corpus was collected and the biases the design carries |

### Code

| Script | Purpose |
|---|---|
| `collect.py`, `reconstruct.py` | discovery, then snapshot-exact refetch by blob id with hash verification |
| `build_corpus.py` | files → `agents.jsonl.gz`, `bodies.jsonl.gz`, `governance.jsonl.gz` |
| `repometa_v2.py` | repository metadata, commit history, branch protection, rulesets, CODEOWNERS |
| `oracles_v2.py` | the executable oracles: resolution, admission, settings, name probes, release history |
| `drift.py` | when each removed tool name disappeared, and when each file was first committed |
| `curation.py` | the engineered-project screen → ALL / E1 / E2 / E3 |
| `llm_labels.py` | annotation batches, validation, merging, Krippendorff's α, the human kit |
| `nlp.py` | directive-sentence extraction, constraint classification, topic model |
| `experiment.py`, `experiment_subagent.py` | the 5 × 6 × 3 × 30 execution experiment and its scorers |
| `analysis_v2.py` | the joined table and RQ1–RQ7 |
| `paper_numbers.py`, `figures_v2.py`, `check_manuscript.py` | the manuscript's numbers, figures and consistency check |
| `lint.py` | the linter |

## Reproduce the paper's numbers

```bash
pip install -r requirements.txt
python3 code/curation.py            # the engineered-project screen
python3 code/analysis_v2.py table   # join everything into data/v2/spec_table.jsonl.gz
python3 code/analysis_v2.py all --pop E2
python3 code/paper_numbers.py       # writes paper/numbers.tex
python3 code/figures_v2.py          # regenerates the figures into paper/
python3 code/check_manuscript.py    # refs, citations, macros and figures all resolve
```

Bootstrap seeds are fixed, so the output is reproducible. A macro `paper_numbers.py` cannot compute is
emitted as a visible `\textbf{??}`, so an unfinished value cannot silently reach the PDF.

## Lint an agent directory

```bash
python3 code/lint.py path/to/.claude/agents
```

Reports specifications the tool will silently ignore, tool names the pinned release does not resolve,
lists that resolve to nothing, an inert `permissionMode`, duplicate names of which only one loads,
fields the tool never reads, and the paper's central finding as a rule: a specification that withholds
file-writing tools while granting an unscoped shell. It exits non-zero on error-level findings, so it
can run in CI.

## Four things to know before reusing this

**Omitting `tools:` is the most permissive choice, not a neutral default.** It inherits the full tool
pool, and 32.9% of specifications in engineered repositories do it. An analysis restricted to
specifications that declare an explicit list conditions on a post-treatment variable and understates
privilege for exactly the roles that omit most often.

**Requested is not effective.** The runtime drops names it does not resolve, resolves aliases, and
**drops `Grep` and `Glob` whenever `Bash` is granted** — which happens to 78.1% of the explicit lists
that name them. Capability here is measured on the tool set the runtime actually resolves, established
by executing it, not by parsing the field. A parser would count capability the tool never granted.

**Repositories are the unit of analysis.** Specifications within a repository are strongly dependent,
so every prevalence is a mean of within-repository proportions with a bootstrap over repositories, and
role contrasts are paired within repository. `code/stats.py` is the only place this is implemented.

**Roles are annotated, not pattern-matched.** Keyword matching reached only about 65% in preliminary
work, so roles, modes and prose restrictions are annotated by language models against published codebooks,
with a second rater on a reliability sample and a two-coder human validation kit. Non-differential
misclassification pulls group rates toward the corpus mean and manufactures a null, so this mattered.

## Oracles

Defect labels come from executing the tool rather than from reading its documentation, with no model
inference and no credential: the `system/init` event reports the resolved tool set and the registered
agents before any inference happens. The oracles establish what resolves, what is admitted, what is
silently dropped, what the settings layer reports, and how the tool vocabulary changed across 48
releases. What they cannot see — launchability, feature-flagged and interactive-only tools — is
reported separately rather than counted as a defect. See `METHOD.md` and the paper's methodology.

## Provenance

All tool behaviour reported here was observed on Claude Code v2.1.233 (macOS arm64 native). The tool
vocabulary changes between releases, so defect rates are version-conditional; the drift analysis
measures that change rather than assuming it away. The corpus is a convenience sample of public
repositories discovered through code search and supports no population estimate.

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
