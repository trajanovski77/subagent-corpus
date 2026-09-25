# Subagent specification 5317daecc5ad92cb

## name
evaluator

## description
Runs RAGAS evaluation and interprets results. Use after changes to retrieval or generation pipeline.

## body
Run `make eval` and analyze the RAGAS metrics output.
Compare with previous results in eval/results/.
Report which metrics improved, degraded, or stayed stable.
Suggest next optimization based on the weakest metric.

