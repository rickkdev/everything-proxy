# Phase 1 reviewed corpus and thread evaluation

- [x] 1. `how` over the affected subsystem.
- [x] 2. `architect` for parallel design exploration.
- [x] 3. Write the throughput checkpoint as four todo items. A dimension that genuinely does not apply (single file, no fan-out) keeps its item with `n/a: <reason>` rather than being dropped:
- [x]    - **Blocking first steps.** Gates run before fan-out.
- [x]    - **Independent workstreams.** Disjoint files, services, or layers parallelize. Shared writes serialize.
- [x]    - **Shared mutable state.** Default to splitting the target (the **separate-before-serializing-shared-state** principle skill). Serialize only for real invariants.
- [x]    - **Smallest safe decomposition.** If one worker is best, name why.
- [ ] 4. Delegate code-writing to a subagent using your configured feature model (default in poteto-mode's Models section) with a specific scope (file paths, named data shape and its organizing structure per **principle-model-the-domain**, a state machine over scattered booleans, a table/registry over branching, a typed model over repeated shape assumptions, chosen before the delegate writes logic, and success criteria). Pick each subagent's reasoning level for the job, per the Subagents section. When the implementation admits multiple valid shapes (error handling, abstraction layer, test structure), delegate via the **arena** skill instead so the runners surface the alternatives and the cross-judge guards the pick. Mandatory: no skip-with-reason escape, and Laziness Protocol does not override it (the gain is review separation, not lines saved). A subagent forbidden to spawn satisfies this by owning the diff directly with the same review separation. No "standing by" reply that waits on a nested agent. **Give every file-writing delegate its own worktree** (spawn it with `isolation: "worktree"`, or hand it an exclusive branch), and do not write files or run a suite in a worktree a delegate still holds. On Claude Code, `isolation: "worktree"` branches from the remote default branch unless the `worktree.baseRef` setting is "head". When the delegate builds on commits the default branch lacks, commit them, create its worktree with `git worktree add <path> -b <delegate-branch> HEAD`, and name that base commit in the brief. Fencing a file in the brief's prose is not a lock (**principle-separate-before-serializing-shared-state**). Comments per **Comments**. Surgical edits, re-ground against the source for upstream-derived files. Port shared-primitive improvements to all consumers and verify each. Commit liberally.
  - skip: Repository AGENTS.md directs one engineer for the initial implementation, so the root engineer wrote the evaluator and scorer.
- [x] 5. Verify on the matching surface. "Inconclusive" or wrong-surface checks stay open. When the deliverable is code the user can see or run, drive the real app, CLI, or server yourself and observe the changed behavior. A file diff, a string search, and a build do not prove behavior. UI work needs a screenshot. Keep every review gate closed without its own evidence, per **principle-prove-it-works**.
- [x] 6. Report the result with the feature's own reply lines.

Implementation stayed with one engineer because repository instructions specify one engineer for the initial implementation. Two independent readers and a cross-judge reviewed the design.

## Architect phases

- [x] Ground
- [x] Sketch
- [x] Agree
- [x] Implement
- [x] Scrap, not needed because the implemented shape matched the reviewed sketch without recurring deviations.

## Arena phases

- [x] Frame
- [x] Fan out
- [x] Cross-judge
- [x] Pick
- [x] Graft
- [x] Verify

## Throughput checkpoint

- [x] Blocking first steps: read Phase 1 plans, trace the reviewed gate, and define thread case shape before changing evaluator or fixtures.
- [x] Independent workstreams: fixtures/labels and gate logic share case IDs and output contracts, so keep them in one engineer's sequence.
- [x] Shared mutable state: one writer owns fixture IDs, reviewed labels, evaluator, results, and `progress.md`.
- [x] Smallest safe decomposition: one engineer completes this bounded evaluation; project instructions specify one engineer and review judgments must bind to retained outputs.

## Task units

- [x] Define a reviewed multi-message thread shape and add representative synthetic threads with expected outcomes.
- [x] Extend the deterministic gate to score ordered thread outputs, cross-message evidence, updates, and prohibited disclosures.
- [x] Run the pinned candidate on the expanded reviewed corpus and preserve outputs plus system and process memory evidence.
- [x] Record case-level results, run aggregate, methodology, limits, and next task in `.audit/` and `progress.md`.
