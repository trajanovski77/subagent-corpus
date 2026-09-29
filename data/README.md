# Corpus — "Specifying the Machine Team"

Snapshot collected 27–28 August 2026, reconstructed **by git blob identifier and verified by hash**,
so each file is the blob that was at that path in that snapshot rather than a later state of the path.
Gzipped JSON Lines. The derived tables support recalculating the reported numbers with `../code/`.
Regenerating text features from the original bodies requires files not included in this GitHub repository.

## The v2 corpus (`v2/`)

| File | Lines | What it is |
|---|---:|---|
| `v2/agents.jsonl.gz` | 94,899 | one record per inventoried `.claude/agents/**.md` file: repo, path, blob id, bytes, recovery status, parsed frontmatter, parse-error flag. **Includes the files that could not be recovered**, marked as such, so the loss is countable |
| `v2/bodies.jsonl.gz` | 69,316 | full specification bodies (163 MB; not included in this GitHub repository) |
| `v2/governance.jsonl.gz` | 4,078 | per repository: `settings.json` permission rules, hooks, MCP servers, CI workflow permissions |
| `v2/engineered.jsonl.gz` | 4,128 | the curation ladder per repository: each screen's outcome and the E1/E2/E3 flags |
| `v2/spec_table.jsonl.gz` | 69,316 | **the analysis table**: every specification joined with its resolved grant, annotation labels, text features, curation flags. This is what `analysis_v2.py` and `figures_v2.py` read |
| `repometa_v2.jsonl.gz` | 4,979 | repository metadata: monthly commit history to the snapshot, contributors, licence, code bytes, branch protection, rulesets, CODEOWNERS, Dependabot, security policy, README |

## Oracle output (`v2/oracles/`)

| File | What it is |
|---|---|
| `resolver_unauth.jsonl` | for each distinct `tools` list in the corpus, the tool set the runtime actually resolves |
| `census.jsonl` | for each configuration root, which specifications the runtime registers and which it silently discards |
| `names_unauth.jsonl` | each distinct tool name probed on its own |
| `name_classes.json` | the resulting classification: resolves / alias / removed_legacy / never_valid / interactive_only / flag_gated / mcp_conditional / platform_conditional / whitespace_split |
| `settings_diagnostics.jsonl` | what the sibling `settings.json` layer reports for the same kinds of mistake |
| `tool_pool_history.jsonl` | the tool vocabulary of 48 released versions |
| `semantics.json`, `builtin_agents.json`, `baseline_unauth.json` | schema-field behaviour and the probe baseline |

`v2/drift_first_commits.jsonl` and `v2/drift_removals.json` date each removed tool name and each file
that names one, which is what separates "written before the removal" from "copied from a stale source
afterwards".

## Annotation (`v2/labels/`, codebooks in `../annotation/`)

| File | Lines | What it is |
|---|---:|---|
| `v2/labels/roles_haiku.jsonl.gz` | 42,004 | role, intended mode, read-only claim, language and boilerplate flag for every distinct (name, description) |
| `v2/labels/readme_haiku.jsonl.gz` | 4,130 | the README category behind Stage B of the curation screen |
| `v2/labels/*/in*/`, `out_*/` | — | the batches as given to the annotators and their raw output, so any label can be traced to its batch, rater and codebook version |
| `v2/labels/roles/agreement.json` | — | Krippendorff's α per field between the two model raters |

Item identity is `sha1(name + "\n" + description)`, so byte-identical specifications across
repositories are labelled once and share the label.

## NLP features (`v2/nlp/`)

`texts.jsonl.gz` and `spec_prose.jsonl.gz` (per-specification prose features),
`directive_sentences.jsonl.gz` (every sentence carrying an RFC 2119-style modality, with its
category), `topics.json` and `item_topics.jsonl.gz` (the topic model), `desc_embeddings.npy`.

## The experiment (`experiment/`)

`schedule.jsonl` is the pre-specified run order; `runs_subagent.jsonl` holds one record per scored run
(configuration, task, model, outcome, the pathway by which the file system was reached, refusals,
permission-layer denials). `runs_authfailed_quarantine.jsonl` holds runs from an earlier attempt whose
session had lost authentication; **they are excluded from every analysis** and kept only so the
exclusion is visible.

## Deriving the study corpus

The unit is a **specification**, not a file. The inclusion rule is the runtime's own admission
requirement — parseable YAML frontmatter declaring both `name` and `description`:

```python
import gzip, json
recs = [json.loads(l) for l in gzip.open('v2/agents.jsonl.gz', 'rt')]
specs = [a for a in recs if a.get('available') and a.get('is_spec')]
# -> 69,316 specifications across 4,128 repositories
```

For anything analytical, read `v2/spec_table.jsonl.gz` instead: it already carries the resolved grant,
the labels and the population flags.

## Three things to know before reusing this

**Capability is the resolved grant, not the `tools` field.** The runtime drops unrecognised names,
resolves aliases, and drops `Grep` and `Glob` whenever `Bash` is granted. `spec_table.jsonl.gz` carries
both `requested` and `effective`; use `effective`, `can_write_files` and `can_shell`. A parser applied
to the raw field will disagree with the tool.

**Omitting `tools` is the largest grant, not a missing value.** It inherits the whole pool. Restricting
an analysis to specifications that declare a list conditions on a post-treatment variable.

**Repositories are the unit of analysis.** Specifications within a repository are strongly dependent;
pooling them and applying a binomial interval understates uncertainty several-fold. Use the
repository-level bootstrap in `../code/stats.py`, and pair role contrasts within repository.

## Provenance and limits

Public GitHub only, discovered via size-partitioned code search, which excludes forks and non-default
branches and truncates every band. This is a convenience sample, not a probability sample; it supports
no population estimate. See the paper's Threats to validity section, and `tab:perils` there, for the
full statement.

All runtime behaviour referenced in the paper was observed on Claude Code v2.1.233 (macOS arm64
native) and is version-conditional — the tool vocabulary changes between releases, which
`v2/oracles/tool_pool_history.jsonl` measures rather than assumes.

## v1

The files from the first version of this study (`agents.jsonl.gz`, `trees.jsonl.gz`,
`repometa.jsonl.gz`, `oracle_agents.jsonl.gz`, `tool_vocab.json`, `results_final.txt`) remain in this
directory for comparison. They are superseded: the v1 fetch stage lost roughly a quarter of the
inventory, its role instrument was a keyword codebook, and its capability measure was our own parser
rather than the runtime. Do not mix them with `v2/`.
