# Bonsai 2 security alert hillclimb

1. Ground the workload and architecture before choosing the metric. Run the **how** skill over the target, name the realistic workload dimensions that can move the result (data size, history, state, concurrency), and select a case that reproduces the user's complaint. If no case reproduces it, fix the repro instead of hillclimbing. Then fix one metric, the direction that counts as better, and a checkable stop predicate that pairs a target with a floor on attempts (the example "at least 50% better than baseline and at least 10 iterations" is this shape). Use the user's numbers when given, otherwise agree them.
2. Build the measurement harness, prove its sensitivity, then freeze it (the **build-the-lever** principle skill). Run contrasting realistic workloads and confirm the target case reproduces the symptom while easier cases separate as expected. If the harness cannot distinguish them, revise the workload or metric. Vet the harness with the **benchmark-checklist** skill before you freeze it, and make it print its error count and a count of the work done. Once frozen, one repeatable command emits the metric, sampled enough to clear the noise (median of N, not a single run). Record the baseline metric and a green run of the regression gate (the tests that must keep passing) before any change.
3. Open the decision log via the **show-me-your-work** skill. A `decision.tsv`, one row per attempt: id, hypothesis, change, before, after, delta, tests, verdict (kept or reverted), note. Read it before each attempt. Keep it out of the tree (gitignored).
4. Ground each hypothesis in the architecture model from step 1, so it names a specific mechanism ("defer X off the boot path because it blocks first paint"), not "try memoizing something". For a perf metric, order hypotheses by the performance mantras in step 2 of the Perf issue playbook (`playbooks/perf-issue.md`). Borrow only their order, not that step's stop rule.
5. Loop, one hypothesis per iteration:
   - Hand the change to a subagent using your configured hillclimb model (default in poteto-mode's Models section) with a tight scope. Pick each subagent's reasoning level for the job, per the Subagents section. Supervise and review the diff rather than typing it (the **guard-the-context-window** principle). When several independent hypotheses are live, fan them to parallel subagents, each in its own worktree (the **separate-before-serializing-shared-state** principle).
   - Measure before and after with the frozen harness, and run the regression gate.
   - Accept only when the metric moves past noise and the gate stays green. Otherwise revert the change in full. A tweak that "might help" is not kept.
   - One commit per accepted fix, staging only the files you changed (`git add <files>`, never `-A`). Log the row either way, kept or reverted.
   Each iteration ends in a check before the next begins (the **sequence-verifiable-units** principle). If the run is unattended, borrow only the wake mechanism from the Autonomous run playbook (`playbooks/autonomous-run.md`), not its stop rule.
6. Push past the first plateau. On a stall, several rejects in a row, pivot category, combine near-misses, re-read the source, or try something more radical before concluding the hill is climbed. Correctness and simplicity outrank the number. Revert a win that breaks behavior, and keep a simplification that holds the number (the **laziness-protocol** principle).
7. Stop when the predicate is met, or when the remaining ideas are marginal and not worth their cost. Don't relax the predicate to meet it, and don't quit while cheap untried hypotheses remain. If you are stuck, surface it instead of spinning.
8. Run **Opening a PR** with the accepted commits stacked in the order they landed.  
   skip: no pull request was requested.

Throughput checkpoint:

- Blocking first steps: reproduce the alert miss and freeze an experiment gate that requires alert recovery, supported evidence, zero prohibited disclosures, preserved date handling, and existing aggregate thresholds.
- Independent workstreams: prompt variants can be screened independently, but model inference shares one local MLX process and will be run sequentially.
- Shared mutable state: model outputs and reviewed adjudications are local synthetic data; each prompt variant gets a separate output directory.
- Smallest safe decomposition: one engineer owns the prompt comparison and manual semantic adjudication so the reviewed gate maps to exact local outputs.

Task-specific checks:

- [x] Inspect actual model flow, baseline prompt, and reproduced security miss.
- [x] Extend the semantic gate to require the security alert and verify hard failures plus ordinary date handling.
- [x] Bind every fact to an exact reviewed claim/evidence pair, reject unreviewed or non-include facts, enforce distinct-fact credit and complete case coverage, and verify hard-failure controls.
- [x] Compare at least two focused prompt changes on the full synthetic corpus; review each distinct output. Both candidates had one full-corpus screening pass.
- [x] Pick one candidate and run five full repeated passes through the frozen gate.
- [x] Record each case, memory evidence, decisions, and next candidate or rejection in `.audit/` and `progress.md`.

Additional skips:

- Hillclimb step 5 delegation. The project plan assigns one engineer for the initial implementation; both prompt variants shared one local MLX runtime and reviewed adjudication file.
- Hillclimb step 5 commit. This checkout reports the project files as untracked, so staging a prompt or script commit could sweep unrelated initial files. No commit was created.
