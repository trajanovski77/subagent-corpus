# Codebook C: what a directive sentence in a subagent specification constrains

Version 1.0, 2026-09-16. Unit of annotation: one sentence from the body (system prompt) of a subagent specification
that contains a prohibition or obligation key word (never, do not, must, always, ensure, ...). The same codebook is
used by LLM and human annotators.

## Field 1 — `topics` (a list: every code that applies; at least one)

| code | the sentence constrains... | examples of the kind of sentence |
|---|---|---|
| FS_MODIFY | creating, editing, writing, overwriting or deleting files or code; being read-only | "Never modify source files." "You must not edit tests." "Only read files." |
| EXEC | running commands, scripts, builds, tests, package installs, shells | "Do not run npm install." "Always run the test suite." |
| VCS | version-control actions: commit, push, merge, branch, rebase, PRs | "Never force-push." "Do not commit." |
| SCOPE | staying within a task, directory, file set, component or role boundary | "Do not touch files outside src/." "Only work on the assigned ticket." |
| SECRETS | credentials, secrets, tokens, .env files, personal or sensitive data | "Never print API keys." |
| EXTERNAL | network or external systems: web access, third-party APIs, production systems, deployment, sending messages | "Do not call production APIs." "Never deploy." |
| DESTRUCTIVE | irreversible or dangerous operations: rm -rf, dropping databases, data loss, resetting history | "Never drop tables." |
| QUALITY | engineering quality and process: tests, types, style, conventions, no placeholders/TODOs/mocks, error handling | "Always add tests." "Do not leave TODOs." |
| OUTPUT | the form of the agent's answer: format, length, structure, language, what to report | "Always respond in JSON." "Do not include explanations." |
| ESCALATE | asking, confirming, reporting back or deferring to the user or parent agent before acting | "Ask before making changes." "Report blockers instead of guessing." |
| HONESTY | not fabricating, not guessing, verifying, citing evidence, admitting uncertainty | "Never invent APIs." "Do not claim success without running tests." |
| DELEGATION | spawning, invoking or coordinating other agents or tools as agents | "Do not spawn subagents." "Always delegate implementation to the coder." |
| OTHER | none of the above (domain content, style of prose, anything else) | "Never use passive voice in blog posts." |

Rules
- Code what is constrained, not the key word. "Always read the file before editing it" is FS_MODIFY (editing is in scope) and QUALITY.
- A sentence can have several topics. Use OTHER only when no other code applies.

## Field 2 — `polarity`

`prohibit` if the sentence forbids or limits an action ("never", "do not", "must not", "only X" as a restriction);
`require` if it demands an action ("must", "always", "ensure"); `other` if it is neither (e.g. describes what the agent
cannot do as a fact, or the key word is used in another sense, "don't worry").

## Field 3 — `restricts_writes` (true/false)

`true` only if the sentence forbids or limits the agent's own creation, modification or deletion of files or code
(including "read-only", "do not edit", "only modify X"). Requirements to write something ("always update the changelog")
are `false`.

## Output format

One JSON object per line, in input order, one line per input item, nothing else:

{"id": "<id copied from input>", "topics": ["<code>", ...], "polarity": "<prohibit|require|other>", "restricts_writes": <true|false>}
