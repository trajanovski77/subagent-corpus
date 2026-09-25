# Codebook P: is a repository an engineered software project?

Version 1.0, 2026-09-16. Unit of annotation: one GitHub repository, presented as its name, description, topics,
languages, star count, number of commits before the snapshot (28 August 2026), contributor count, creation date,
template flag, and the first 3,000 characters of its README. The same codebook is used by LLM and human annotators.

Adapted from the engineered-project notion of Munaiah et al. (2017) and the README-based LLM screening of
Galster et al. (2026): an engineered project is one that "leverages sound software engineering practices in one or
more of its dimensions such as documentation, testing, and project management" and exists to build or maintain
software that is used, rather than to store, teach, demonstrate or distribute material.

## Field 1 — `category` (choose exactly one)

| code | assign when the repository primarily is... | signals |
|---|---|---|
| ENGINEERED | a software product, library, service, tool, application, framework or infrastructure that is developed and maintained to be used | README describes what the software does, how to install/run it; real code languages; multiple commits over time |
| TEMPLATE_COLLECTION | a collection or distribution of agents, prompts, skills, commands, rules, configs or boilerplate meant to be copied into other projects (including "awesome" lists, starter kits, plugin marketplaces) | "collection of N agents", "copy these into .claude/", "install these subagents", catalogue READMEs |
| TUTORIAL_LEARNING | course material, tutorials, exercises, workshop or book companion code, homework, learning notes | "course", "tutorial", "learn", "exercise", "workshop", "lesson" |
| PERSONAL_CONFIG | a personal setup: dotfiles, one person's Claude Code / editor / AI tooling configuration, personal knowledge base or notes | "my dotfiles", "my Claude setup", "personal workflow", "my notes" |
| DEMO_EXPERIMENT | a toy, demo, prototype, hackathon entry, proof of concept, playground or weekend experiment not maintained as a product | "demo", "playground", "hackathon", "POC", "experiment", very few commits |
| NON_SOFTWARE | content that is not software: documentation-only sites, writing, research papers, business documents, marketing content, data dumps | README about a book, blog, company knowledge, reports |
| UNCLEAR | cannot be decided from the information given (e.g. empty README and uninformative metadata) | |

Rules
- Decide by the repository's *primary purpose*. A product repository that also ships agent files for its own development
  is ENGINEERED. A repository whose main content is agent files for others to copy is TEMPLATE_COLLECTION.
- An empty or missing README is not by itself a reason for UNCLEAR if the name, description, languages and commits make the
  purpose clear.
- Young repositories can be ENGINEERED; do not penalise age alone. Do not decide from star counts alone.
- A framework or tool *for building agents* (an SDK, an orchestration runtime, a CLI) is ENGINEERED; a set of prompt
  files is TEMPLATE_COLLECTION.

## Field 2 — `confidence`: `high`, `medium` or `low`.

## Output format

One JSON object per line, in input order, one line per input item, nothing else:

{"id": "<id copied from input>", "category": "<code>", "confidence": "<high|medium|low>"}
