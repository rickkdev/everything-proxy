# Phase 3 local persistence checklist

## Feature playbook

1. `how` over the affected subsystem.
2. `architect` for parallel design exploration.
3. Write the throughput checkpoint as four todo items. A dimension that genuinely does not apply (single file, no fan-out) keeps its item with `n/a: <reason>` rather than being dropped:
   - **Blocking first steps.** Gates run before fan-out.
   - **Independent workstreams.** Disjoint files, services, or layers parallelize. Shared writes serialize.
   - **Shared mutable state.** Default to splitting the target (the **separate-before-serializing-shared-state** principle skill). Serialize only for real invariants.
   - **Smallest safe decomposition.** If one worker is best, name why.
4. Delegate code-writing to a subagent using your configured feature model (default in poteto-mode's Models section) with a specific scope (file paths, named data shape and its organizing structure per **principle-model-the-domain**, a state machine over scattered booleans, a table/registry over branching, a typed model over repeated shape assumptions, chosen before the delegate writes logic, and success criteria). Pick each subagent's reasoning level for the job, per the Subagents section. When the implementation admits multiple valid shapes (error handling, abstraction layer, test structure), delegate via the **arena** skill instead so the runners surface the alternatives and the cross-judge guards the pick. Mandatory: no skip-with-reason escape, and Laziness Protocol does not override it (the gain is review separation, not lines saved). A subagent forbidden to spawn satisfies this by owning the diff directly with the same review separation. No "standing by" reply that waits on a nested agent. **Give every file-writing delegate its own worktree** (spawn it with `isolation: "worktree"`, or hand it an exclusive branch), and do not write files or run a suite in a worktree a delegate still holds. On Claude Code, `isolation: "worktree"` branches from the remote default branch unless the `worktree.baseRef` setting is "head". When the delegate builds on commits the default branch lacks, commit them, create its worktree with `git worktree add <path> -b <delegate-branch> HEAD`, and name that base commit in the brief. Fencing a file in the brief's prose is not a lock (**principle-separate-before-serializing-shared-state**). Comments per **Comments**. Surgical edits, re-ground against the source for upstream-derived files. Port shared-primitive improvements to all consumers and verify each. Commit liberally.
5. Verify on the matching surface. "Inconclusive" or wrong-surface is not a pass. Flag it.
6. Rebase into small, ordered commits. Stack follow-ups.
   Use the **sequence-verifiable-units** principle, building, verifying, and committing each small unit before the next.
7. If the design is contested, `interrogate` before shipping.
8. Run **Opening a PR**.

## Throughput checkpoint

- **Blocking first steps.** Bonsai candidate measurements and Phase 1 blocker are recorded before production processing work.
- **Independent workstreams.** n/a: one bounded SQLite persistence unit owns the schema and update semantics.
- **Shared mutable state.** No parallel writers; SQLite transactions serialize updates per connection.
- **Smallest safe decomposition.** One engineer owns this unit because the initial implementation is one narrow schema boundary and repo instructions specify one engineer.

## Data shape

`MessageUpdate` contains an internal account key, provider message and thread keys, a source revision hash, received timestamp, retention deadline, and in-scope state. SQLite normalizes current thread revisions, messages, and filter decisions. An unchanged update is a no-op. A changed source increments its revision and the thread context revision. Out-of-scope or expired sources invalidate dependent local state.

## Work

- [x] Read current storage and thread behavior. No production storage module existed; the reviewed schema is `.audit/phase2-data-model.md`.
- [x] Add the smallest local SQLite persistence module for idempotent thread/message updates, policy invalidation, and retention cleanup.
- [x] Verify replay, source/thread changes, stale policy/rule rejection, invalidation, expiry, and a two-connection policy update serialized ahead of a stale result check using synthetic metadata only. `python scripts/verify_local_store.py` passes; output is `.audit/local-store-verification.json`.
- [x] Update `build-plan.md` and `progress.md` only when acceptance evidence exists.
