# Corpus — "Specifying the Machine Team"

Snapshot collected 27–28 August 2026. Gzipped JSON Lines; 28 MB compressed, 135 MB raw.
Every number in the paper is reproducible from these files plus `../code/` (`python3 code/analyze.py`).

| File | Lines | What it is |
|---|---:|---|
| `agents.jsonl.gz` | 67,927 | one record per `.claude/agents/**.md` file: repo, path, bytes, sha256 prefix, parsed frontmatter fields, parse-error flag, first 400 chars of body |
| `trees.jsonl.gz` | 4,979 | one record per repository: full config-file inventory from the Git Trees API (agents, skills, commands, settings, CLAUDE.md, AGENTS.md, .mcp.json, CI workflows) |
| `repometa.jsonl.gz` | 3,008 | repository metadata for every spec-bearing repo: stars, forks, fork/archived flags, created/pushed dates, licence, language |
| `oracle_agents.jsonl.gz` | 1,591 | O1 acceptance-oracle results: declared vs harness-accepted agent names per repository (seeded random sample) |
| `repos.txt` | 4,979 | the discovery frame — every repository found by size-partitioned code search |
| `partitions.jsonl` | 28 | stage-1 query log, one record per size band: reported total, pages retrieved, distinct repositories, truncation flag, timestamp (see *The query log* below) |
| `provenance.json` | — | run manifest: counts computed from these files, tool build, known biases, and the note on the query log |
| `repos_rerun_2026-08-28.txt` | 12,251 | repositories discovered by the stage-1 re-run that produced `partitions.jsonl` |
| `tool_vocab.json` | — | O2 output: 30 valid and 30 invalid tool names, established against the harness |
| `results_final.txt` | — | output of `code/analyze.py`; the paper's numbers are taken from it |
| `figsummary.json` | — | numbers behind the figures, written by `code/figures.py` |

## The query log

The per-band query log of the original stage-1 run was not archived. `partitions.jsonl` is the log
of a re-run of stage 1 with the same 28 size bands on 28 August 2026 (12:14–12:48 UTC), the second
day of the snapshot. It shows that **every band is truncated**: reported totals range from 1,032 to
14,016 files against the 1,000 results per band the interface returns, 220,220 matching files in
all. The re-run discovered 12,251 repositories (`repos_rerun_2026-08-28.txt`), among them 4,950 of
the 4,979 repositories in the archived frame (99.4%); the remaining 7,301 are repositories the
original run did not reach. The archived frame is therefore a subset of what the interface serves,
which is why the paper treats the corpus as a convenience sample and makes no population estimate.
The tree inventories and agent files in this directory cover the 4,979 frame repositories only.
`provenance.json` records all of this; regenerate it with
`python3 ../code/collect.py --provenance-only --snapshot 2026-08-27/2026-08-28`.

## Deriving the study corpus

The paper's unit is a **specification**, not a file. The inclusion rule is the harness's own
admission requirement — parseable YAML frontmatter declaring both `name` and `description`:

```python
import gzip, json
recs = [json.loads(l) for l in gzip.open('agents.jsonl.gz', 'rt')]
specs = [a for a in recs
         if not a.get('fm_error') and a.get('name') and a.get('description')]
# -> 50,011 specifications across 3,008 repositories
```

## Two things to know before reusing this

**The `tools` field must be re-normalised from `tools_raw`.** The `tools` key stored in
`agents.jsonl.gz` was written by an early parser that split on whitespace, which mangles entries like
`Bash(npm run build)`. Every analysis script re-derives it from `tools_raw` with the corrected
splitter (`normalise_tools()` in `../code/parsing.py`; `parsing.load_records()` applies it for you).
Use that function, not the stored field.

**Repositories are the unit of analysis.** Specifications within a repository are strongly dependent
(ICC 0.41, design effect 6.34). Pooling specifications and applying a binomial interval understates
uncertainty roughly six-fold. Use the repository-level bootstrap in `../code/stats.py`.

## Provenance and limits

Public GitHub only, discovered via size-partitioned code search, which excludes forks and truncates
partitions at a fixed page depth. This is a convenience sample, not a probability sample; it supports
no population estimate. See the paper's Threats to validity section for the full statement.

All harness behaviour referenced in the paper was observed on Claude Code v2.1.233, commit
`f8d57569aaf3`, and is version-conditional — the tool vocabulary changes between releases.
