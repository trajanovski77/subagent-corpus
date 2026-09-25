# Human validation kit v2 (codebooks R, S, B and P)

Two coders independently code 400 items with the same codebooks and texts the language models saw:

| part | items | question | codebook | time |
|---|---|---|---|---|
| R | 200 (name, description) pairs | role, intended mode, explicit read-only claim | `codebook_roles.md` | 30-40 min |
| S | 80 whole specifications | does the prose restrict the agent's own writes? (full / partial / none) | `codebook_spec_restriction.md` | 40-60 min |
| B | 60 whole specifications | the most state-changing shell use the text asks for (change / verify / inspect / none) | `codebook_shell_use.md` | 35-50 min |
| P | 60 repositories (metadata and README) | what the repository primarily is (seven categories) | `codebook_repositories.md` | 35-50 min |

## For coders

1. Open `coder.html` in a desktop browser (double-click it; it works offline and sends nothing anywhere). Type your initials.
2. Code **independently**. Do not discuss items, do not use AI tools, and do not look at the other coder's or the
   models' labels (`model_labels_*.jsonl`) until both files are exported. You need only `coder.html`.
3. Keys: press `Keys` in the page. R: role letter, then mode `i/c/m/u`, then read-only claim `y/n`. S: `f/p/n`.
   B: `c/v/i/n`. P: `e/t/l/p/d/s/u`. `Enter` moves on. `Codebook` shows the full rules; the side panel shows the rules
   for the current part.
4. Progress is saved in the browser; you can stop and come back in the same browser. `?` flags an item you are unsure
   about. You still give your best label.
5. Press **Export** when you finish, and whenever you pause. It downloads `human_<initials>.json`. `Load file`
   continues from an export if you change browser or computer.
6. Send the final `human_<initials>.json` to the lead author.

## For the lead author

7. Put both `human_<initials>.json` files in this folder (`annotation/human_v2/`).
8. From the repository root, run `python3 code/human_agreement.py`. It prints the tables and writes `agreement.json`
   here. `--selftest` checks the pipeline on fabricated coders.
9. The sample is fixed (seeds 20260923 to 20260926, one per part). To rebuild it, run
   `python3 annotation/human_v2/build_kit.py`. The build is deterministic, and the sample digest shown in each export
   must match `sample_meta.json`.
10. Only after both exports: meet, adjudicate the disagreements, and record the adjudicated labels separately. Never
    edit the exported files.
11. Report human-human alpha as the reliability of each codebook, and consensus-vs-model alpha as the validity of the
    LLM labels. Part P has no Sonnet labels (codebook P had one model rater), and only 5 of the 60 part-B items have a
    Sonnet label, so B and P are compared with Haiku, the primary rater whose labels the paper uses.
