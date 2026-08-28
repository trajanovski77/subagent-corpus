# How the corpus was collected

This is the answer to "how did you get all of them?", written so that a reviewer can check it
and a stranger can repeat it.

```bash
gh auth login          # once
python3 code/collect.py   # three stages, resumable, writes provenance.json
```

## The constraint that shapes everything

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
would serve. That last flag is written to `data/partitions.jsonl`, so truncation is a measured quantity in
the replication package rather than an invisible property of the method. The log shipped with the
corpus was recorded on 28 August 2026 by re-running stage 1 (the original run's log was not archived);
it re-found 99.4% of the archived frame and shows every band truncated.

**Stage 2, exhaustive per-repository inventory.** For each discovered repository we make a single Git
Trees API call, which returns the repository's entire file list in one request and is not subject to
the search cap. Everything matching `.claude/agents/**.md` is recorded, along with the other
configuration artifacts used for the co-occurrence analysis. **Within a discovered repository the
file inventory is exhaustive.** This is the step that makes the per-repository census defensible, and
it is why prevalence figures (which are within-repository proportions) are far more robust than the
team-size distribution.

**Stage 3, fetch and parse.** Raw bytes are fetched for every agent file and the YAML frontmatter is
parsed. Records keep the raw `tools` value alongside the normalised one, so a reader can re-derive
the field with a different parser.

## What this sample is, and is not

It is a **convenience sample of repositories**, not a probability sample. It supports statements about
the repositories in it, and no population estimate. Three biases are recorded in `provenance.json`
and stated in the paper:

- **Forks and non-default branches are excluded**, because code search does not index them.
- **Discovery is file-level.** A repository with many agent files has more chances to surface than one
  with few, so the repository sample is size-biased toward large agent teams. This inflates the
  team-size distribution; it barely touches within-repository proportions.
- **Every band truncates.** All 28 bands report more results than the 1,000 the interface serves
  (220,220 matching files in total), so the repositories discovered from each band are a subset and
  the frame under-samples the matching population: a same-day re-query retrieved 12,251 repositories
  against the 4,979 in the frame. `data/partitions.jsonl` records the per-band totals.

## Why the unit of analysis is the repository

Specifications inside one repository are strongly dependent (ICC 0.41, design effect 6.34 for the
write/execute outcome). Pooling 50,011 specifications and applying a binomial interval would
understate uncertainty roughly six-fold. Every prevalence figure in the paper is a mean of
per-repository proportions with a percentile bootstrap over repositories.

## Reproducibility notes

- The script is **idempotent and resumable**: re-running continues from what is on disk and re-fetches
  nothing. Interrupting it is safe.
- Runtime is dominated by rate limits, not compute: code search allows roughly 10 requests per minute,
  the core API 5,000 per hour. A full run is a few hours.
- Numbers will not reproduce *exactly* on a later run, because the population grows. The snapshot used
  in the paper is dated in `provenance.json` and archived in `data/`.
- Tool behaviour reported in the paper was observed on Claude Code v2.1.233, commit `f8d57569aaf3`.
  The tool vocabulary changes between releases, so defect rates are version-conditional.
