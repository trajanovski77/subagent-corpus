"""Parsing and normalisation of subagent specifications.

One module owns every decision about how a raw ``.claude/agents/*.md`` file becomes a
record, so the collector, the oracles and the analysis cannot drift apart.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

FRONTMATTER = re.compile(r"\A﻿?---\s*\n(.*?)\n---\s*(\n|$)", re.S)

#: Frontmatter keys the tool documents. Anything else is a non-schema field.
SCHEMA_FIELDS = frozenset({
    "name", "description", "tools", "disallowedTools", "model", "permissionMode",
    "maxTurns", "skills", "mcpServers", "hooks", "memory", "background",
    "isolation", "color", "effort", "initialPrompt",
})

#: Field names that look like ``tools`` but are never read by the tool. ``allowed-tools`` is
#: valid frontmatter for slash commands, not subagents; a specification using it and omitting
#: ``tools:`` expresses a restriction the tool never applies and inherits the full pool.
NEAR_MISS_FIELDS = frozenset({"allowed-tools", "allowedTools", "allowed_tools", "tools_allowed"})

#: Tool names earlier releases shipped and later removed. Separating these from
#: never-valid names distinguishes artifact/runtime drift from authoring error.
LEGACY_TOOLS = frozenset({
    "MultiEdit", "LS", "View", "Replace", "NotebookRead", "TodoRead",
    "GlobTool", "GrepTool", "SlashCommand", "StickerRequest", "WebFetchTool", "Cd",
})

#: Operational definitions of "can change things", from narrowest to broadest.
#: ``primary`` is the one the paper leads with.
WRITE_SETS = {
    "narrow":  frozenset({"Write", "Edit", "NotebookEdit"}),
    "primary": frozenset({"Write", "Edit", "NotebookEdit", "Bash", "PowerShell"}),
    "broad":   frozenset({"Write", "Edit", "NotebookEdit", "Bash", "PowerShell",
                          "Agent", "Task", "Skill", "EnterWorktree"}),
}


def normalise_tools(value: Any) -> list[str] | None:
    """Split a ``tools:`` value into individual grants.

    Comma is the real separator. A parenthesised specifier such as
    ``Bash(npm run build)`` must not be split on its inner spaces, which is the bug
    an earlier version of this code had.

    Returns ``None`` when the field is absent, which is semantically distinct from an
    empty list: omitting ``tools:`` inherits the *full* tool pool.
    """
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(x).strip() for x in value]
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text in ("*", "all"):
            return ["*"]
        items = ([x.strip() for x in text.split(",")] if "," in text
                 else re.findall(r"[A-Za-z_][\w.-]*\([^)]*\)|\S+", text))
    else:
        items = [str(value)]
    return [x for x in items if x]


def base_tool(grant: str) -> str:
    """Strip a permission specifier: ``Bash(npm run x)`` becomes ``Bash``."""
    m = re.match(r"^([A-Za-z_][\w.-]*)\s*\(", grant)
    return m.group(1) if m else grant


def is_known_tool(grant: str, vocabulary: Iterable[str]) -> bool:
    """Whether a grant resolves to a tool the pinned build recognises.

    MCP tools are accepted by construction: they are namespaced per server and cannot
    be validated without that server's manifest. See ``docs/ORACLES.md`` for why the
    vocabulary oracle is sound only for names without underscores.
    """
    stem = base_tool(grant)
    return stem in vocabulary or stem.startswith("mcp__") or grant.startswith("mcp__") or stem == "*"


def grants_capability(spec: dict, write_set: str = "primary") -> bool:
    """Whether a specification can perform a write or execute action *at all*.

    Measured unconditionally. Omitting ``tools:`` counts as holding the capability,
    because omission inherits the full pool. Conditioning on "declares an explicit
    list" would condition on a post-treatment variable that is itself part of the
    outcome, and would understate privilege for exactly the roles that omit most.
    """
    tools = spec.get("tools")
    if tools is None or tools == ["*"]:
        return True
    return bool({base_tool(t) for t in tools} & WRITE_SETS[write_set])


def declares_tools(spec: dict) -> bool:
    """Whether the specification declares a real, enumerated tool list."""
    tools = spec.get("tools")
    return tools not in (None, ["*"]) and bool(tools)


def parse_specification(repo: str, path: str, raw: str) -> dict:
    """Turn one raw file into a corpus record.

    Both the raw and the normalised ``tools`` value are kept so a reader can re-derive
    the field with a different parser. ``name`` and ``description`` are stored exactly
    as parsed, including the rare cases where YAML yields a list or dict, so the corpus
    records what was actually written rather than what we wish had been.
    """
    import yaml  # imported lazily so the module is usable without PyYAML installed

    rec: dict[str, Any] = {
        "repo": repo,
        "path": path,
        "bytes": len(raw),
        "hash": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16],
    }
    m = FRONTMATTER.match(raw)
    if not m:
        rec["fm_error"] = "no-frontmatter"
        rec["body_head"] = raw.strip()[:400]
        return rec

    body = raw[m.end():]
    rec["body_chars"] = len(body.strip())
    rec["body_head"] = body.strip()[:400]
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        rec["fm_error"] = "yaml-error"
        return rec
    if not isinstance(fm, dict):
        rec["fm_error"] = "fm-not-dict"
        return rec

    for key in ("name", "description", "model", "permissionMode", "maxTurns",
                "memory", "background", "isolation", "color", "effort", "initialPrompt"):
        if key in fm:
            rec[key] = fm[key]
    rec["tools_raw"] = fm.get("tools")
    rec["tools"] = normalise_tools(fm.get("tools"))
    rec["disallowedTools"] = normalise_tools(fm.get("disallowedTools"))
    rec["skills"] = normalise_tools(fm.get("skills"))
    rec["mcpServers"] = normalise_tools(fm.get("mcpServers"))
    rec["has_hooks"] = bool(fm.get("hooks"))
    rec["fm_keys"] = sorted(str(k) for k in fm.keys())
    return rec


def split_frontmatter(raw: str) -> tuple[str | None, str]:
    """Return (frontmatter text or None, body). The body is what the tool uses as the system prompt."""
    m = FRONTMATTER.match(raw)
    if not m:
        return None, raw
    return m.group(1), raw[m.end():]


def locate(path: str) -> dict:
    """Where a file sits relative to its ``.claude/agents`` directory.

    ``config_root`` is the directory holding ``.claude/`` ("" for the repository root). Claude Code loads
    project agents from the ``.claude/agents`` directory of the directory it is started in, so two files
    with the same name under *different* roots never compete; under the same root they do.
    """
    root, _, rel = path.rpartition(".claude/agents/")
    return {"config_root": root.rstrip("/"), "rel_path": rel, "nested": "/" in rel,
            "root_is_repo_root": root == ""}


def is_specification(rec: dict) -> bool:
    """The corpus inclusion rule: the tool's own admission requirement.

    A file under ``.claude/agents/`` is a *specification* only if its frontmatter
    parses and declares both ``name`` and ``description``. Everything else in that
    directory (README.md, SKILL.md, notes) is not a specification, and one repository
    in an early snapshot contributed 7,175 files of which 5,087 were exactly that.
    """
    return bool(not rec.get("fm_error") and rec.get("name") and rec.get("description"))


def load_records(path: str | Path) -> list[dict]:
    """Read a corpus file, transparently handling gzip, and repair the ``tools`` field.

    The stored ``tools`` value in archived corpora was written by an earlier parser
    that split on whitespace. We always re-derive it from ``tools_raw``.
    """
    path = Path(path)
    opener = __import__("gzip").open if path.suffix == ".gz" else open
    with opener(path, "rt") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    for rec in records:
        if "tools_raw" in rec:
            rec["tools"] = normalise_tools(rec.get("tools_raw"))
    return records


def specifications(path: str | Path) -> list[dict]:
    """Load a corpus file and return only the records that are specifications."""
    return [r for r in load_records(path) if is_specification(r)]


def iter_jsonl(path: str | Path) -> Iterator[dict]:
    """Stream a possibly-gzipped JSON Lines file."""
    path = Path(path)
    opener = __import__("gzip").open if path.suffix == ".gz" else open
    with opener(path, "rt") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)
