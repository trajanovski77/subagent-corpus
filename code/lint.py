#!/usr/bin/env python3
"""Lint a directory of subagent specifications against the semantics the paper measures.

    python3 code/lint.py [PATH ...]          # default: .claude/agents in the current directory

Every check is one of the defect classes or the least-privilege inconsistency reported in
"Specifying the Machine Team", implemented with the same parsing and vocabulary the analysis
uses (``parsing.py``, ``data/tool_vocab.json``), so the linter and the paper cannot disagree.
The tool itself emits no diagnostic for any of these; this script prints the warning it does
not. Exit status is 1 if any error-level finding was reported, else 0.

Levels
  error  the file is silently ignored, or a declared restriction is void
  warn   the specification is unlikely to do what its author intended
  info   a fact about the specification worth knowing (omission inherits the full pool)

Checks
  D1  not a specification: no frontmatter, unparseable YAML, or missing name/description
      -> the tool ignores the file without saying so
  D2  names a tool the pinned release does not recognise (D2a: removed legacy name,
      D2b: never-valid name)                       [tool vocabulary is version-conditional]
  D3  names no recognised tool at all
  D4  sets permissionMode                            [inert when the parent runs in auto mode]
  D5  model value not recognised
  D6  two or more files declare the same name        -> all but one are silently discarded
  P1  withholds Write/Edit/NotebookEdit but grants an unscoped shell (Bash or PowerShell)
      -> the restriction is void; the shell can write any file
  P2  omits tools: entirely                          -> inherits the full tool pool
  N1  uses a field the tool does not read (e.g. allowed-tools instead of tools)
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parsing  # noqa: E402

DEFAULT_VOCAB = Path(__file__).resolve().parent.parent / "data" / "tool_vocab.json"
NEAR_MISS = parsing.NEAR_MISS_FIELDS | {"tool"}
MODEL_OK = re.compile(r"^(opus|sonnet|haiku|fable|inherit|claude-)", re.I)
SHELLS = {"Bash", "PowerShell"}


def lint_dir(root: Path, vocabulary: set[str]) -> list[tuple[str, str, str, str]]:
    """Return findings as (path, level, code, message)."""
    findings: list[tuple[str, str, str, str]] = []
    names: dict[str, list[str]] = collections.defaultdict(list)
    files = sorted(p for p in root.rglob("*.md") if p.is_file())
    if not files:
        findings.append((str(root), "info", "--", "no .md files found"))
        return findings

    for path in files:
        rel = str(path.relative_to(root.parent)) if root.parent != path else str(path)
        raw = path.read_text(encoding="utf-8", errors="replace")
        spec = parsing.parse_specification("", rel, raw)
        add = lambda level, code, msg: findings.append((rel, level, code, msg))

        if not parsing.is_specification(spec):
            why = spec.get("fm_error") or (
                "missing `name`" if not spec.get("name") else "missing `description`")
            add("error", "D1", f"not a specification ({why}); the tool ignores this file silently")
            continue

        names[str(spec["name"]).strip()].append(rel)

        for key in set(spec.get("fm_keys", [])) - parsing.SCHEMA_FIELDS:
            hint = "; did you mean `tools:`?" if key in NEAR_MISS else ""
            add("warn", "N1", f"field `{key}` is not read by the tool{hint}")

        if spec.get("permissionMode") is not None:
            add("info", "D4", "permissionMode is ignored when the parent session runs in auto mode")
        if spec.get("model") is not None and not MODEL_OK.match(str(spec["model"])):
            add("warn", "D5", f"model `{spec['model']}` is not a recognised value")

        tools = spec.get("tools")
        if tools is None or tools == ["*"]:
            add("info", "P2", "no `tools:` list: inherits every tool available to subagents")
            continue

        bases = {parsing.base_tool(t) for t in tools}
        unknown = [t for t in tools if not parsing.is_known_tool(t, vocabulary)]
        for t in unknown:
            legacy = parsing.base_tool(t) in parsing.LEGACY_TOOLS
            add("warn", "D2a" if legacy else "D2b",
                f"tool `{t}` is {'a removed legacy name' if legacy else 'not a known tool'} in this release")
        if tools and len(unknown) == len(tools):
            add("warn", "D3", "no entry in `tools:` resolves to a known tool")

        writes = bases & parsing.WRITE_SETS["narrow"]
        unscoped_shell = [t for t in tools if parsing.base_tool(t) in SHELLS and "(" not in t]
        if not writes and unscoped_shell:
            add("error", "P1",
                f"withholds file-writing tools but grants unscoped {', '.join(sorted(set(unscoped_shell)))}: "
                "the restriction is void (a shell can write any file); scope it, e.g. Bash(git diff:*)")

    for name, paths in names.items():
        if len(paths) > 1:
            for rel in paths:
                findings.append((rel, "error", "D6",
                                 f"name `{name}` is declared by {len(paths)} files; only one will load"))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=[".claude/agents"], help="agent directories to lint")
    ap.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB, help="tool vocabulary (O2 output)")
    ap.add_argument("--quiet-info", action="store_true", help="suppress info-level findings")
    args = ap.parse_args()
    vocabulary = set(json.loads(args.vocab.read_text())["valid"])

    status = 0
    for p in args.paths:
        root = Path(p)
        if not root.is_dir():
            print(f"{p}: not a directory", file=sys.stderr)
            status = 1
            continue
        for path, level, code, msg in lint_dir(root, vocabulary):
            if level == "info" and args.quiet_info:
                continue
            print(f"{path}: {level}: {code}: {msg}")
            if level == "error":
                status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
