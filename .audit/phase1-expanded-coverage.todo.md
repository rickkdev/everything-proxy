# Phase 1 expanded thread coverage todo

## Feature playbook

1. `how` over the affected subsystem. Done by reading the thread fixture contract, evaluator, scorer, and prior Phase 1 thread design.
2. `architect` for parallel design exploration. skip: the existing ordered-thread data shape already fit the added cases, and the repository requires one engineer for the initial implementation.
3. Write the throughput checkpoint as four todo items. Done below.
4. Delegate code-writing to a subagent using your configured feature model (default in poteto-mode's Models section) with a specific scope (file paths, named data shape and its organizing structure per **principle-model-the-domain**, a state machine over scattered booleans, a table/registry over branching, a typed model over repeated shape assumptions, chosen before the delegate writes logic, and success criteria). Pick each subagent's reasoning level for the job, per the Subagents section. When the implementation admits multiple valid shapes (error handling, abstraction layer, test structure), delegate via the **arena** skill instead so the runners surface the alternatives and the cross-judge guards the pick. Mandatory: no skip-with-reason escape, and Laziness Protocol does not override it (the gain is review separation, not lines saved). A subagent forbidden to spawn satisfies this by owning the diff directly with the same review separation. No "standing by" reply that waits on a nested agent. **Give every file-writing delegate its own worktree** (spawn it with `isolation: "worktree"`, or hand it an exclusive branch), and do not write files or run a suite in a worktree a delegate still holds. On Claude Code, `isolation: "worktree"` branches from the remote default branch unless the `worktree.baseRef` setting is `"head"`. When delegates build on commits the default branch lacks, commit them, create their worktree with `git worktree add <path> -b <delegate-branch> HEAD`, and name that base commit in the brief. Fencing a file in the brief's prose is not a lock (**principle-separate-before-serializing-shared-state**). Surgical edits, re-ground against the source for upstream-derived files. Port shared-primitive improvements to all consumers and verify each. Commit liberally. skip: the repository requires one engineer for the initial implementation, and the active runtime forbids unrequested subagent delegation.
5. Verify on the matching surface. Done with the local evaluator, reviewed scorer, and nine negative controls.
6. Rebase into small, ordered commits. Stack follow-ups. skip: no commit or PR was requested; the task remains local and reviewable.
7. If the design is contested, `interrogate` before shipping. skip: no contested design remained; the existing ordered checkpoint model was retained.
8. Run **Opening a PR**. skip: the user did not authorize PR operations.

## Throughput checkpoint

- [x] Blocking first steps. The Phase 1 pipeline gate blocks Phase 3. The fixture contract and local pinned runtime were available before the screen.
- [x] Independent workstreams. n/a: fixture cases, adjudications, and scoring outputs share IDs and one ordered dataset.
- [x] Shared mutable state. One writer updated the fixtures, labels, scorer verifier, and evidence in sequence.
- [x] Smallest safe decomposition. One engineer kept the fixture, reviewed output labels, and retained reports consistent; the repository asks for one engineer.

## Task

- [x] Add two reviewed five-message synthetic threads covering date revisions, changing task state, completion, source evidence, and stale facts.
- [x] Screen the pinned local candidate once and retain outputs and cumulative memory evidence.
- [x] Score the outputs without approving missed or stale facts. Preserve the failing gate result.
- [x] Update the verifier for expanded coverage and pass its nine negative controls.
- [x] Update `build-plan.md`, the Phase 1 evaluation notes, and `progress.md` with the remaining Phase 1 blocker.
