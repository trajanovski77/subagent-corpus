"""Estimation for clustered corpus data.

Specifications are not independent observations. They arrive in repositories, and
within a repository they are usually written by one person in one sitting, often from
one template. For the write/execute outcome the intra-class correlation is 0.41 and the
design effect 6.34, so pooling specifications and applying a binomial interval
understates uncertainty roughly six-fold.

Every prevalence figure in the paper is therefore a **mean of per-repository
proportions** with a **percentile bootstrap over repositories**. This module is the only
place that decision is implemented.
"""
from __future__ import annotations

import math
import random
import statistics as st
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

DEFAULT_SEED = 20260828
DEFAULT_REPLICATES = 10_000


@dataclass(frozen=True)
class Estimate:
    """A repository-weighted proportion with its bootstrap interval."""
    mean: float          #: mean of per-repository proportions (the reported estimate)
    lo: float            #: lower bound, percentile bootstrap over repositories
    hi: float            #: upper bound
    median: float        #: median per-repository proportion
    n_repos: int         #: repositories contributing
    pooled: float        #: naive specification-level rate, for contrast only
    numerator: int
    denominator: int

    def __str__(self) -> str:
        return (f"{100*self.mean:5.1f}%  95% CI [{100*self.lo:4.1f},{100*self.hi:4.1f}]"
                f"  n={self.n_repos:>5d} repos   (pooled {100*self.pooled:5.1f}%)")


def bootstrap_ci(values: Sequence[float], replicates: int = DEFAULT_REPLICATES,
                 alpha: float = 0.05, seed: int = DEFAULT_SEED) -> tuple[float, float]:
    """Percentile bootstrap over the clustering unit.

    ``values`` must be one number per repository, not one per specification. Resampling
    repositories with replacement is what propagates between-repository variance into
    the interval; resampling specifications would not.
    """
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(sum(vals[int(rng.random() * n)] for _ in range(n)) / n
                   for _ in range(replicates))
    return means[int(alpha / 2 * replicates)], means[int((1 - alpha / 2) * replicates) - 1]


def wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval, valid only for genuinely binomial counts.

    Use this for repository-level counts (how many repositories are affected), never
    for a mean of per-repository proportions. Applying it to the latter was a real bug
    in an earlier version of this analysis.
    """
    if trials == 0:
        return (0.0, 0.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    margin = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def by_repository(specs: Iterable[dict]) -> dict[str, list[dict]]:
    """Group specifications by their repository."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for spec in specs:
        grouped[spec["repo"]].append(spec)
    return dict(grouped)


def estimate(specs: Iterable[dict],
             predicate: Callable[[dict], bool],
             population: Callable[[dict], bool] | None = None,
             seed: int = DEFAULT_SEED) -> Estimate | None:
    """Repository-weighted proportion of specifications satisfying ``predicate``.

    ``population`` restricts the denominator (for example, to specifications that
    declare an explicit tool list). Be careful with it: restricting the denominator to
    a post-treatment variable induces collider bias. See ``grants_capability``.
    """
    grouped = by_repository(specs)
    proportions, numerator, denominator = [], 0, 0
    for records in grouped.values():
        eligible = [r for r in records if population(r)] if population else records
        if not eligible:
            continue
        hits = sum(1 for r in eligible if predicate(r))
        proportions.append(hits / len(eligible))
        numerator += hits
        denominator += len(eligible)
    if not proportions:
        return None
    lo, hi = bootstrap_ci(proportions, seed=seed)
    return Estimate(mean=st.mean(proportions), lo=lo, hi=hi,
                    median=st.median(proportions), n_repos=len(proportions),
                    pooled=numerator / denominator if denominator else 0.0,
                    numerator=numerator, denominator=denominator)


def paired_contrast(specs: Iterable[dict],
                    group_a: Callable[[dict], bool],
                    group_b: Callable[[dict], bool],
                    outcome: Callable[[dict], bool],
                    seed: int = DEFAULT_SEED) -> dict | None:
    """Difference in outcome rate between two groups, paired within repository.

    Pairing controls for repository-level authoring style: the same person wrote both
    specifications, so a difference between them cannot be explained by house habits.
    Only repositories containing both groups contribute.
    """
    a_by_repo: dict[str, list[int]] = defaultdict(list)
    b_by_repo: dict[str, list[int]] = defaultdict(list)
    for spec in specs:
        if group_a(spec):
            a_by_repo[spec["repo"]].append(1 if outcome(spec) else 0)
        if group_b(spec):
            b_by_repo[spec["repo"]].append(1 if outcome(spec) else 0)
    shared = sorted(set(a_by_repo) & set(b_by_repo))
    if len(shared) < 10:
        return None
    diffs = [sum(b_by_repo[r]) / len(b_by_repo[r]) - sum(a_by_repo[r]) / len(a_by_repo[r])
             for r in shared]
    lo, hi = bootstrap_ci(diffs, seed=seed)
    return {"difference": st.mean(diffs), "lo": lo, "hi": hi,
            "n_repos": len(shared), "excludes_zero": not (lo <= 0 <= hi)}


def intraclass_correlation(groups: Sequence[Sequence[int]]) -> dict | None:
    """One-way ICC and design effect for a binary outcome clustered by repository.

    Reported in the paper because the magnitude is a finding in its own right: it says
    how badly an analysis that ignored clustering would mislead.
    """
    groups = [g for g in groups if len(g) >= 2]
    if not groups:
        return None
    total = sum(len(g) for g in groups)
    k = len(groups)
    mean_size = total / k
    grand = sum(sum(g) for g in groups) / total
    msb = sum(len(g) * (st.mean(g) - grand) ** 2 for g in groups) / (k - 1)
    msw = sum(sum((x - st.mean(g)) ** 2 for x in g) for g in groups) / (total - k)
    denom = msb + (mean_size - 1) * msw
    icc = (msb - msw) / denom if denom else float("nan")
    deff = 1 + (mean_size - 1) * icc
    return {"icc": icc, "design_effect": deff, "n_specs": total, "n_repos": k,
            "mean_cluster": mean_size, "effective_n": total / deff if deff else float("nan")}


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1          # average rank for ties
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation with average ranks for ties (no SciPy dependency).

    Used to check whether the file-size truncation of the discovery frame can confound a
    measure: a quantity uncorrelated with file size is not affected by size-band truncation.
    """
    rx, ry = _ranks(x), _ranks(y)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")
