"""Assigning a delegated role to a specification.

Two instruments, and the difference between them matters.

``broad_role`` is a keyword codebook over the name and description. It labels most of
the corpus but scored only about 65% on a 25-item validation sample, with false
positives such as "test **data**" reading as a database role and "**optimis**ing"
reading as refactoring.

That accuracy is not good enough for the paper's central comparison, and the reason is
specific rather than general: non-differential misclassification pulls every group rate
toward the corpus mean, so a noisy classifier *manufactures* a finding of "role does not
matter". A null result from a noisy instrument is unfalsifiable.

``strict_role`` therefore trades recall for precision. It fires only when the ``name``
field contains exactly one unambiguous role token, and returns ``None`` on ambiguity, so
``security-reviewer`` is dropped rather than arbitrarily assigned to whichever pattern
happens to be listed first. The headline contrast is computed on this subset.
"""
from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- broad
#: (role, name pattern, description pattern). The name is weighted far above the
#: description, and generic triggers ("data", "optimise", "developer") were removed
#: after validation showed them driving most false positives.
BROAD_PATTERNS: list[tuple[str, str, str]] = [
    ("review/audit",  r"\b(review(er)?|audit(or|ing)?|critic|inspector|linter)\b",
                      r"\b(code review|reviews? (the )?code|audits?)\b"),
    ("test",          r"\b(test(er|ing)?|tdd|qa|e2e|spec-?writer)\b",
                      r"\b(unit test|integration test|test suite|coverage)\b"),
    ("security",      r"\b(security|sec|vuln(erability)?|threat|pentest|appsec)\b",
                      r"\b(vulnerabilit|security (review|audit)|owasp|injection)\b"),
    ("docs",          r"\b(doc(s|umentation)?|readme|changelog|writer|scribe)\b",
                      r"\b(documentation|write (the )?docs|changelog)\b"),
    ("architecture",  r"\b(architect(ure)?|adr|design(er)?)\b",
                      r"\b(architectur|design decision|system design)\b"),
    ("debug/fix",     r"\b(debug(ger)?|bug|fix(er)?|troubleshoot|triage|resolver)\b",
                      r"\b(debug|fix(es|ing)? (bugs|errors|issues)|root cause)\b"),
    ("implement",     r"\b(implement(er|ation)?|coder|builder|developer|engineer|generator|writer)\b",
                      r"\b(implement(s|ing)?|writes? code|builds?)\b"),
    ("refactor",      r"\b(refactor(er)?|cleanup|optimizer|simplifier)\b",
                      r"\b(refactor|clean ?up|reduce (complexity|duplication))\b"),
    ("data/db",       r"\b(database|db|sql|migration|etl|schema|query)\b",
                      r"\b(database|sql|schema|query plan)\b"),
    ("devops/infra",  r"\b(devops|infra(structure)?|deploy(ment)?|docker|k8s|kubernetes|terraform|ci|cd|release|ops)\b",
                      r"\b(deploy|infrastructur|pipeline|kubernetes|terraform)\b"),
    ("frontend",      r"\b(frontend|ui|ux|react|vue|svelte|css|styling)\b",
                      r"\b(front-?end|user interface|component)\b"),
    ("backend/api",   r"\b(backend|api|server|endpoint|microservice)\b",
                      r"\b(back-?end|rest api|endpoint)\b"),
    ("research",      r"\b(research(er)?|explorer?|investigator|analyst|scout)\b",
                      r"\b(research|investigat|explores?)\b"),
    ("planning",      r"\b(plan(ner)?|orchestrat(or)?|coordinator|manager|lead|supervisor|dispatcher)\b",
                      r"\b(orchestrat|coordinat|plans? (the )?work|delegat)\b"),
    ("ml/ai",         r"\b(ml|ai|llm|prompt|model|embedding|rag)\b",
                      r"\b(machine learning|llm|prompt engineering)\b"),
    ("mobile",        r"\b(mobile|android|ios|flutter|swift|react-?native)\b",
                      r"\b(mobile app|android|ios)\b"),
]

# -------------------------------------------------------------------------- strict
#: A single unambiguous token in the ``name`` field. Ambiguity yields ``None``.
STRICT_PATTERNS: list[tuple[str, str]] = [
    ("reviewer",    r"(^|[-_ ])(code[-_ ]?)?review(er)?([-_ ]|$)|(^|[-_ ])auditor([-_ ]|$)"),
    ("security",    r"(^|[-_ ])(security|appsec|pentest(er)?|vulnerability)([-_ ]|$)"),
    ("docs",        r"(^|[-_ ])(doc|docs|documentation)([-_ ]|$)|technical[-_ ]?writer|doc[-_ ]?writer"),
    ("tester",      r"(^|[-_ ])(test(er)?|qa|test[-_ ]?writer|test[-_ ]?runner|test[-_ ]?automator)([-_ ]|$)"),
    ("implementer", r"(^|[-_ ])(implementer|developer|coder|builder)([-_ ]|$)"),
    ("debugger",    r"(^|[-_ ])(debugger|bug[-_ ]?fixer|fixer|troubleshooter)([-_ ]|$)"),
    ("architect",   r"(^|[-_ ])architect([-_ ]|$)"),
    ("planner",     r"(^|[-_ ])(planner|orchestrator|coordinator)([-_ ]|$)"),
]

#: Roles whose stated purpose is to look at code rather than change it.
INSPECTION_ROLES = frozenset({"reviewer", "security", "docs"})
#: Roles whose stated purpose is to change code.
CHANGE_ROLES = frozenset({"implementer", "debugger"})


def _text(value: Any) -> str:
    """Coerce a frontmatter value to text. A handful of specifications declare ``name``
    as a YAML list or dict; those are kept in the corpus rather than dropped."""
    return value if isinstance(value, str) else ("" if value is None else str(value))


def broad_role(name: Any, description: Any) -> str | None:
    """Highest-scoring role from the keyword codebook, or ``None``.

    Accuracy is roughly 65%; use only for description, never for the headline contrast.
    """
    n = _text(name).lower().replace("-", " ").replace("_", " ")
    d = _text(description).lower()
    best, best_score = None, 0
    for role, name_pat, desc_pat in BROAD_PATTERNS:
        score = (10 if re.search(name_pat, n) else 0) + (3 if re.search(desc_pat, d) else 0)
        if score > best_score:
            best, best_score = role, score
    return best


def strict_role(spec: dict) -> str | None:
    """Role from an unambiguous token in ``name``, or ``None`` if absent or ambiguous.

    Returning ``None`` on ambiguity is deliberate. Breaking ties by pattern order would
    silently assign every ``security-reviewer`` to whichever of the two came first, and
    would concentrate that error in exactly the safety-relevant roles.
    """
    name = _text(spec.get("name")).lower().replace("_", "-")
    hits = [role for role, pattern in STRICT_PATTERNS if re.search(pattern, name)]
    return hits[0] if len(hits) == 1 else None


def label(specs: list[dict]) -> list[dict]:
    """Attach ``broad_role`` and ``strict_role`` to each specification in place."""
    for spec in specs:
        spec["role_broad"] = broad_role(spec.get("name"), spec.get("description"))
        spec["role_strict"] = strict_role(spec)
    return specs
