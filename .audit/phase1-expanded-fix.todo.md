# Expanded screen diagnosis todo

## Investigation playbook

1. Route through the **how** skill. Done by reading the thread evaluator, scorer, verifier, fixtures, and retained expanded result.
2. Throughput checkpoint stays one line: `throughput checkpoint: n/a, read-only investigation`. Done.
3. Produce the **how**-shaped output (Overview / Key Concepts / How It Works / Where Things Live / Gotchas), or a recommendation with a tradeoffs table if the investigation is a decision between alternatives. Done in `.audit/phase1-expanded-fix-diagnosis.md`.
4. Apply the **unslop** skill to the reply. Done.

## Task

- [x] Reproduce the expanded gate and its nine negative controls using retained synthetic outputs.
- [x] Trace the count, completion, and postponed-date failures to their source.
- [x] Decide whether a local change can clear the failures without weakening privacy checks or changing reviewed labels.
- [x] Record the blocker and next unchecked task in `progress.md`.

## Throughput checkpoint

`throughput checkpoint: n/a, read-only investigation`
