# Human validation kit v2 (codebooks R and S)

1. Open `coder.html` in a desktop browser (double-click it; it works offline and sends nothing anywhere). Type your initials.
2. Code **independently**. Do not discuss items, or look at the other coder's or the models' labels (`model_labels_*.jsonl`), until both files are exported.
3. Part R (200 items, about 30-40 min): press a role letter, then mode `i/c/m/u`, then read-only claim `y/n`. The next item opens by itself. Part S (80 specifications, about 40-60 min): `f/p/n`, then `Enter`. Press `Keys` for all shortcuts, and `Codebook` for the full rules.
4. Progress is saved in the browser. You can stop and come back in the same browser. `?` flags an item you are unsure about. You still give your best label.
5. Press **Export** when you finish, and whenever you pause. It downloads `human_<initials>.json`. `Load file` continues from an export if you change browser.
6. Put both `human_<initials>.json` files in this folder (`annotation/human_v2/`).
7. From the repository root, run `python3 code/human_agreement.py`. It prints the tables and writes `agreement.json` here. `--selftest` checks the pipeline on fabricated coders.
8. The sample is fixed (seed 20260923). To rebuild it, run `python3 annotation/human_v2/build_kit.py`. The build is deterministic, and the sample digest shown in each export must match `sample_meta.json`.
9. Only after both exports: meet, adjudicate the disagreements, and record the adjudicated labels separately. Never edit the exported files.
10. Report human-human alpha as the reliability of the codebook. Report consensus-vs-model alpha as the validity of the LLM labels.
