# Codebook B: what does a specification ask its agent to use a shell for?

Version 1.0, 2026-09-23. Unit of annotation: one whole subagent specification (`name`, `description`, body). Every
specification in this sample grants a shell (`Bash`) but no file-writing tool; the tool list is not shown to you.
The question is whether the **text** gives the agent a reason to run shell commands, and of what kind. It is
not a question about what the agent should be allowed to do.

## Field 1 — `shell_use` (the most state-changing use the text asks for or clearly implies)

| value | the text asks the agent to run commands that... | examples |
|---|---|---|
| `change` | create, modify, move or delete files, or change the state of the repository, environment or external systems | "run `npm install`", "commit the result", "run `prettier --write`", "apply the migration", "deploy", "generate the client code", `sed -i`, `mkdir`, writing a report file with `>` or `tee` |
| `verify` | build, test, lint, type-check, benchmark or run the program to observe its behaviour, without asking it to change anything | "run the test suite", "run `tsc --noEmit`", "execute `cargo clippy`", "check that the build passes", "run the script and report the output" |
| `inspect` | only read or query state: version-control history, file listing and search, status and diagnostics | `git log`, `git diff`, `git blame`, `git status`, `ls`, `find`, `grep`/`rg`, `cat`, `wc`, `gh pr view`, `kubectl get`, `curl` GET of a status page |
| `none` | the text never mentions running commands, a terminal, scripts, tests or tools that would need a shell | a reviewer that "reads the code and reports issues"; a planner; a writer |

Rules
- Choose the **highest** applicable value in the order change > verify > inspect > none.
- Running tests or builds is `verify` even though test runners write caches; it is `change` only if the text asks the
  agent to fix, install, format, commit, generate or otherwise change something by command.
- A command mentioned only as an example for the *user* or for another agent ("tell the user to run X") does not count.
- Generic phrases such as "use the available tools" or "investigate the codebase" are `none` unless a command-line
  activity is named.
- If the text forbids the agent to run commands ("do not run any commands"), code `none`.

## Field 2 — `evidence`

The shortest verbatim quote (at most 200 characters) supporting the value; empty string for `none`.

## Output format

One JSON object per line, in the order of `index.txt`, one line per specification, nothing else:

{"id": "<id from the file name>", "shell_use": "<change|verify|inspect|none>", "evidence": "<quote or empty>"}
