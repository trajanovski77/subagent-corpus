# How the corpus was collected and measured

This is the answer to "how did you get all of them, and how do you know what they do?", written so
that a reviewer can check it and a stranger can repeat it.

```bash
gh auth login                       # once
python3 code/collect.py             # discovery + exhaustive per-repository inventory
python3 code/reconstruct.py         # refetch every inventoried file by blob id, verify by hash
python3 code/build_corpus.py        # -> data/v2/agents.jsonl.gz and friends
python3 code/repometa_v2.py rest && python3 code/repometa_v2.py graphql && python3 code/repometa_v2.py merge
python3 code/oracles_v2.py resolver census semantics settings history names
```

## The constraint that shapes discovery

GitHub's code-search API is the only public index of file *contents*. It has two properties that
make it unusable as a sampling frame on its own:

1. it serves at most 1,000 results per query (10 pages of 100), and
2. its reported `total_count` is unreliable for large result sets.

A single query for `path:.claude/agents extension:md` therefore cannot enumerate the population, and
any study that treats one such query as its corpus is silently working with a truncated head of the
result list.

## What we do instead

**Stage 1, discovery.** We partition the query space by file size into 28 bands and run one query per
band. Bands are used only to discover *repository names*. For every band we record the reported
total, the number of pages actually retrieved, and whether the reported total exceeded what the API
would serve, so truncation is a measured quantity in the replication package rather than an invisible
property of the method.

**Stage 2, exhaustive per-repository inventory.** For each discovered repository we make a single Git
Trees API call, which returns the repository's entire file list in one request and is not subject to
the search cap. Everything matching the configuration patterns is recorded. **Within a discovered
repository the file inventory is exhaustive.** This is what makes the per-repository census
defensible, and it is why prevalence figures (within-repository proportions) are far more robust than
the team-size distribution.

**Stage 3, snapshot-exact reconstruction.** Every inventoried file is fetched **by its git blob
identifier**, not from a moving branch head, and verified by recomputing the git object hash. A file
that cannot be recovered (its repository or object no longer exists) is retained in the data with its
status rather than dropped, so the loss is visible and countable. This replaces an earlier fetch stage
that silently returned nothing on any exception and lost roughly a quarter of the inventory.

## Measuring capability: execute, do not parse

The `tools` field is not the grant. The runtime resolves it: it drops names it does not recognise,
resolves aliases, and **drops `Grep` and `Glob` whenever `Bash` is present**. A study that parses the
field measures its own parser.

The oracles therefore run the tool itself. Claude Code's stream-json output emits a `system/init`
event that reports the resolved tool set and the registered agents **before any inference happens**,
so a probe needs no model call and no credential: with an isolated `CLAUDE_CONFIG_DIR` and the
`ANTHROPIC_*` variables stripped, the process reaches init and can be read. Each oracle answers one
question:

| oracle | question |
|---|---|
| `resolver` | given this `tools` list, which tools does the runtime actually grant? |
| `census` | given this configuration root, which specifications are registered, and which are silently discarded? |
| `names` | is this individual tool name resolvable, an alias, removed, never valid, or context-conditional? |
| `settings` | what does the sibling `settings.json` layer report for the same kinds of mistake? |
| `history` | how did the tool vocabulary change across releases? |
| `semantics` | what do the schema fields do on this build? |

**What the oracles cannot see** is reported separately rather than counted as a defect: they observe
registration and resolution, not launchability; feature-flagged tools are invisible to a
credential-free probe; interactive-only tools cannot appear in print mode at all; and `PowerShell`
resolves on Windows but not here.

## Curation: which repositories count

Mining public GitHub without a screen measures personal scratch repositories. We apply a
**pre-registered** engineered-project filter (`annotation/engineered_filter_protocol.md`,
`code/curation.py`) in two stages: a metadata screen (not a fork/archive/template/mirror; at least 50
commits; at least 3 active months; a commit within six months of the snapshot; at least 10 kB of
source) and a README classification against a published codebook. Every headline quantity is reported
under four nested populations — ALL, E1, E2, E3 — rather than one, so a reader can see which claims
depend on the screen. Table `tab:perils` in the paper maps each of Kalliamvakou's perils of mining
GitHub to what it would do to our conclusions and what we did about it.

## Annotation

Roles, intended modes, prohibition categories, README categories, whole-specification write restrictions
(codebook S, one specification per engineered repository) and experiment completion claims (codebook K) are
annotated by language models
against published codebooks (`annotation/codebook_*.md`), one item at a time, with the model seeing
only the codebook and the item. Batches, validation, merging, agreement and the human kit are all in
`code/llm_labels.py`. A bulk rater labels everything; a second model re-labels a stratified
reliability sample; Krippendorff's α is reported per field; and a blank two-annotator kit
(`annotation/human_roles/`) is provided for human validation. Item identity is
`sha1(name + "\n" + description)`, so byte-identical specifications across repositories are labelled
once and share the label.

Keyword matching reached only about 65% in preliminary work, which is why annotation is by codebook.
Non-differential misclassification pulls group rates toward the corpus mean and manufactures a finding
that role does not matter, so the instrument mattered to the conclusion.

## What this sample is, and is not

It is a **convenience sample of repositories**, not a probability sample. It supports statements about
the repositories in it, and no population estimate.

- **Forks and non-default branches are excluded**, because code search does not index them.
- **Discovery is file-level.** A repository with many agent files has more chances to surface than one
  with few, so the repository sample is size-biased toward large agent teams. This inflates the
  team-size distribution; it barely touches within-repository proportions.
- **Every band truncates.** All 28 bands report more results than the 1,000 the interface serves, so
  the frame under-samples the matching population.
- **Specifications are duplicated across repositories**, so repositories are not independent
  observations either; a one-copy-per-content-hash sensitivity analysis accompanies the headline
  contrasts.

## Why the unit of analysis is the repository

Specifications inside one repository are strongly dependent. Pooling them and applying a binomial
interval understates uncertainty several-fold. Every prevalence figure is a mean of per-repository
proportions with a percentile bootstrap over repositories, and every role contrast is **paired within
repository**, so a difference between two kinds of delegate cannot be explained by one team's house
style. `code/stats.py` is the only place this is implemented.

## The execution experiment

Static grants say what is permitted; they do not say what happens. The experiment crosses five
configurations (unrestricted, prompt-only, tools-only, tools+prompt, no-shell) with six tasks, three
models and repeated trials, in randomised order, each run in a fresh context with a fresh fixture
directory, scored **from the file system** rather than from the agent's report. Contrasts are
pre-specified and tested with Fisher's exact test with Holm adjustment. Permission-layer denials are
extracted from the transcripts and reported separately, so the session's own gating cannot be mistaken
for an effect of the grant.

## Reproducibility notes

- The collection scripts are **idempotent and resumable**: re-running continues from what is on disk.
- Runtime is dominated by rate limits, not compute. A full collection is a few hours.
- Numbers will not reproduce *exactly* on a later run, because the population grows. The snapshot used
  in the paper is the one archived in `data/`, and it is snapshot-exact by construction: every file is
  the blob that was there, verified by hash.
- Bootstrap seeds are fixed. `code/paper_numbers.py` emits every quantity the manuscript quotes, and a
  quantity it cannot compute becomes a visible `\textbf{??}` rather than a stale number.
- Tool behaviour reported in the paper was observed on Claude Code v2.1.233 (macOS arm64 native). The
  tool vocabulary changes between releases, so defect rates are version-conditional; `code/drift.py`
  measures that change across 48 releases rather than assuming it away.
