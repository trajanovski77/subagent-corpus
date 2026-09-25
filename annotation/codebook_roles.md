# Codebook R: the delegated role of a subagent specification

Version 1.1, 2026-09-16 (1.0 piloted on 400 items; 1.1 adds the placeholder, security, language and boilerplate rules below). Unit of annotation: one (name, description) pair taken from a specification's frontmatter.
The same codebook is used by the LLM annotators and by the human annotators, so every rule below is written
to be applied by a person reading the text.

Judge only from the `name` and `description` given. Descriptions may be in any language, and may be
truncated (ending in "…"). Do not guess from outside knowledge of a repository.

## Field 1 — `role` (choose exactly one: the primary function the agent is delegated)

| code | role | assign when the agent's main job is to... | typical signals |
|---|---|---|---|
| REQ | requirements & product | elicit, write or review requirements, specs, user stories, PRDs, acceptance criteria, product decisions | spec writer, product manager, story, PRD, EARS |
| ARCH | architecture & design | design systems, APIs, data models, component structure; write ADRs; make technical design decisions | architect, system design, ADR, DDD |
| IMPL | implementation | write, build or extend code or features (any language, framework, layer: frontend, backend, mobile, full-stack, "X expert/pro/developer/engineer") | developer, engineer, builder, implement, "expert in Go" |
| TEST | testing & QA | write, run, plan or analyse tests; QA; coverage; test strategy | tester, test writer, QA, e2e, TDD |
| REVIEW | code review & quality audit | review code, PRs or implementations for quality, correctness, style or standards; lint; quality gates | reviewer, code review, auditor (non-security), quality |
| SEC | security | security review, vulnerability analysis, threat modelling, pentesting, security/compliance audits | security, vulnerability, OWASP, pentest, HIPAA audit |
| DEBUG | debugging & fixing | diagnose and fix bugs, errors, failures, incidents | debugger, bug fixer, troubleshoot, root cause |
| REFACT | refactoring & maintenance | refactor, clean up, reduce technical debt, upgrade/migrate code or dependencies | refactor, cleanup, tech debt, migration of code |
| DOCS | documentation | write or maintain documentation, READMEs, API docs, changelogs, comments, knowledge bases | docs writer, documentation, changelog |
| OPS | DevOps & infrastructure | CI/CD, deployment, release, cloud, containers, infrastructure as code, monitoring, SRE | deploy, CI, Kubernetes, Terraform, release |
| DATA | data, databases & ML/AI | data engineering, databases/SQL, analytics, ML/LLM engineering, prompt engineering, evaluation | database, SQL, ETL, ML, LLM, prompt |
| UX | UX & visual design | UX research, UI/visual design, design systems as design, accessibility review | UX researcher, visual designer, accessibility audit |
| EXPLORE | research & exploration | search or map a codebase, gather information, research the web, analyse and summarise | explorer, researcher, analyst, summariser, scout |
| PLAN | planning & orchestration | plan work, break tasks down, coordinate or dispatch other agents, manage a workflow or project | planner, orchestrator, coordinator, manager, lead |
| NONSE | not software engineering | a domain task outside software engineering: marketing, sales, legal, finance, content/creative writing, customer support, education, personas of people, games narrative, weather lookup | marketing, SEO content, APA citation, persona of a philosopher |
| UNCLEAR | unclear | the text is too short, generic or garbled to tell | "agent", "helper", a name with no description |

Tie-breaking rules
- UI *implementation* (building components, pages) is IMPL; UX *research or visual design* is UX.
- "Review and fix" or "find and fix": if fixing is the stated end goal, DEBUG; if the output is findings, REVIEW.
- A security-focused reviewer is SEC, not REVIEW.
- Database schema design is DATA unless the text is about overall system architecture (ARCH).
- A language or framework "expert/pro/specialist" with no other stated job is IMPL.
- An orchestrator of a specific activity (e.g. "refactor pipeline coordinator") is PLAN.
- SEO: technical SEO of a website's code is OPS or IMPL as described; SEO/marketing content writing is NONSE.
- Any security-focused agent is SEC, whether it reviews, tests or builds security features (authentication, encryption, access control).
- Placeholder or template text that does not describe a real agent ("AGENT_NAME", "Brief description of what this agent does", "TODO") is UNCLEAR with mode unclear.
- Image, audio, video or document processing tools used inside software products are DATA if they are about data/ML processing, otherwise IMPL; they are NONSE only when the task is not about building or operating software (e.g. writing a presentation's content).

## Field 2 — `mode` (choose exactly one: what fulfilling the stated purpose requires)

| code | assign when |
|---|---|
| inspect | The purpose can be fulfilled without creating, modifying or deleting any file and without running commands that change state. The agent reads, searches, analyses, reviews, plans or advises, and returns its result as a message. |
| change | The purpose requires creating, modifying or deleting files (code, tests, docs, configs, reports written to disk) or running operations with side effects (deploying, migrating, committing, installing). |
| mixed | The description explicitly combines both (e.g. "analyses X and applies fixes", "reviews and updates docs"). |
| unclear | Cannot tell. |

Rules
- Decide from what the agent is asked to *produce*, not from its role label. A reviewer that "writes a report
  to docs/review.md" is `change`; a planner that "returns a plan" is `inspect`; one that "writes plan.md" is `change`.
- Running tests or analysis commands that only report results is `inspect`; generating, fixing or formatting code is `change`.
- Orchestrators that only dispatch other agents are `inspect` unless they are also said to edit or commit.

## Field 3 — `readonly_claim` (true/false)

`true` only if the name or description explicitly says the agent is read-only, must not / does not modify, edit or
write files, or makes no changes (e.g. "Read-only reviewer", "Never modifies files", "Does not propose changes"
counts only if it says it does not *make* changes). Otherwise `false`.

## Field 4 — `lang`

ISO 639-1 code of the language most of the description's natural-language words are in (`en`, `zh`, `ko`, `ja`, `ru`, `es`,
`pt`, `fr`, `de`, `it`, `vi`, `tr`, ...). Technical terms and product names do not count: "Turn-based dialogue simulation giữa
Solo Developer và End User" is `vi`. Use `xx` if there is no natural-language text.

## Field 5 — `boilerplate` (true/false)

`true` only if the description is evidently produced by filling a generic template with the agent's name or category,
recognisable by placeholder-like repetition or a fixed boilerplate frame (e.g. "Assist with X operations. Auto-activating
skill for Y. Triggers on: X, X. Part of the Y skill category."). A well-known or widely copied description that is otherwise
specific ("Use this agent to implement frontend features following component-based architecture") is `false`: copying is
measured separately from the corpus, not by this field. When in doubt, `false`.

## Output format

One JSON object per line, in input order, one line per input item, nothing else:

{"id": "<id copied from input>", "role": "<code>", "mode": "<inspect|change|mixed|unclear>", "readonly_claim": <true|false>, "lang": "<code>", "boilerplate": <true|false>}
