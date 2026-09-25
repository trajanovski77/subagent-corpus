# Engineered-project curation protocol (fixed before any outcome was inspected)

Written 2026-09-16, before repository metadata collection finished and before any README label, role label or
capability outcome was joined to repository metadata. Changing a threshold after this point must be reported as a
deviation. Implemented in `code/curation.py`.

## Why a filter, and why three of them

Kalliamvakou et al. (2014, 2016) show that most GitHub repositories are personal, inactive or not software
development, and the ACM SIGSOFT Repository Mining standard lists unfiltered open-source convenience samples as an
antipattern. A subagent specification in a toy, tutorial, template dump or abandoned experiment may not reflect how
practitioners configure agents for real work. Galster et al. (2026) therefore screened repositories with metadata
thresholds and a README classifier before analysing agent configuration.

Their thresholds (at least 271 or 352 commits, 6 or 7 watchers, created at least 18 months earlier) target mature
projects and would remove almost the entire subagent population, which post-dates the introduction of the format in
mid-2025. We keep their structure (metadata screening, then README classification) and adapt the activity thresholds
to the age of the ecosystem, and we report the headline results under three nested definitions so that the effect of
each curation decision is visible rather than hidden in one choice.

## Stage A: metadata screening (heuristic thresholds), all measured up to the snapshot (2026-08-28)

| # | criterion | threshold | peril / dimension addressed |
|---|---|---|---|
| A1 | not a fork, not archived, not disabled, not a template repository, not a mirror, not empty | all false | Kalliamvakou I; GitHub metadata |
| A2 | commit history | at least 50 commits on the default branch before the snapshot | Kalliamvakou II (low activity); Munaiah history |
| A3 | lifecycle span | commits in at least 3 distinct calendar months (of the 36 observed) | not a one-off dump; PHANTOM's time-series view |
| A4 | recency | at least one commit in the 6 months before the snapshot | Kalliamvakou III (inactive); reaper "state" 6 months |
| A5 | code | at least 10 kB of source detected by GitHub Linguist | Kalliamvakou IV (not software) |

Lifecycle descriptors (reported, not used as filters): `single_burst` if at least 80% of observed commits fall in one
month; `sustained` if active in at least half of the months since the first observed active month and at least 3
months; `dormant` if no commit in the last 6 months.

## Stage B: README classification

Every specification-bearing repository is classified from its name, description, topics, languages, star count,
commit count, contributor count, creation date, template flag and README (first 3,000 characters) using codebook P
(`annotation/codebook_repositories.md`). Categories: ENGINEERED, TEMPLATE_COLLECTION, TUTORIAL_LEARNING,
PERSONAL_CONFIG, DEMO_EXPERIMENT, NON_SOFTWARE, UNCLEAR. Primary rater: Claude Sonnet 5; second rater on a random
reliability sample: Claude Haiku 4.5; human validation sample: two annotators (kit in `annotation/human_readme/`).

## Populations

| name | definition | role in the paper |
|---|---|---|
| ALL | every specification-bearing repository | comparison with the original study; sensitivity |
| E1 | Stage A passes | activity-based sensitivity |
| **E2** | Stage A passes and Stage B = ENGINEERED | **primary population for every headline result** |
| E3 | E2 and at least 2 contributors and a licence | strict, Galster-like sensitivity (Kalliamvakou V personal projects) |

## Pre-declared analyses of curation itself
- Counts removed at each step, for repositories and specifications.
- Headline quantities (grant type, capability by intended mode, incoherent restriction rate, prose-grant inconsistency,
  silent-defect rates) under ALL, E1, E2 and E3, with bootstrap intervals.
- README label agreement between the two LLM raters (Krippendorff's alpha) and, when available, with humans.
