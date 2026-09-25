# Codebook S: does a subagent specification's prose restrict the agent's own writes?

Version 1.0, 2026-09-23. Unit of annotation: one whole subagent specification — its `name`, its `description` and its
body (the system prompt). The same codebook is used by LLM and human annotators.

The question is about what the **text** tells the agent, not about its tool list. Ignore the frontmatter `tools` field
entirely; it is not shown to you and it is not what is being measured.

"Writes" means the agent's own creation, modification, overwriting or deletion of files or code, and running commands
whose purpose is to change files (e.g. `git commit`, `rm`, a formatter run with `--write`, `sed -i`).

## Field 1 — `restriction`

| value | the prose... | examples |
|---|---|---|
| `full` | forbids the agent **all** writes, or says it is read-only / only analyses, reviews, reports or advises and does not change anything itself | "You are read-only." "Never modify any files; report findings only." "Your job is to review, not to edit code." "Do not make changes — return recommendations to the parent agent." |
| `partial` | forbids or conditions **some** writes but leaves others allowed | "Never modify test files." "Do not edit files outside `src/`." "Do not delete files." "Ask before editing configuration." "Only modify the files you were assigned." |
| `none` | places no restriction on the agent's own writes | an implementer told to write code; a reviewer whose text never says whether it may edit; restrictions only on *other* things (secrets, network, git push, output format) |

Rules
- Judge the agent's **own** writes. "Do not push to main" restricts version control, not file writes → not by itself `partial`.
  "Never commit" *is* `partial` (committing changes the repository).
- A purpose statement alone ("reviews code for bugs") is **not** a restriction. It becomes `full` only if the text says
  or clearly implies the agent must not change things itself ("…and reports them; it does not fix them").
- If the text both forbids writes in general and allows a narrow exception ("read-only, except you may write your report
  to `reports/`"), code `partial`.
- If the body contains a template for *other* agents or example prompts, judge only the instructions addressed to this agent.
- Requirements to write ("always update the changelog") are not restrictions.

## Field 2 — `evidence`

The shortest verbatim quote (at most 200 characters) from the text that supports `full` or `partial`. Empty string for `none`.

## Field 3 — `where`

`description`, `body`, or `both` — where the supporting text is. Empty string for `none`.

## Output format

One JSON object per line, in the order of `index.txt`, one line per specification, nothing else:

{"id": "<id from the file name>", "restriction": "<full|partial|none>", "evidence": "<quote or empty>", "where": "<description|body|both|empty>"}
