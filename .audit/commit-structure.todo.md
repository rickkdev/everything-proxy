# Commit existing project work

- [x] 1. `how` over the affected subsystem.
- [x] 2. `architect` for parallel design exploration.
- [x] 3. Write the throughput checkpoint as four todo items.
- [x] 4. Delegate code-writing to a subagent using your configured feature model (default in poteto-mode's Models section) with a specific scope (file paths, named data shape and its organizing structure per **principle-model-the-domain**, a state machine over scattered booleans, a table/registry over branching, a typed model over repeated shape assumptions, chosen before the delegate writes logic, and success criteria). Pick each subagent's reasoning level for the job, per the Subagents section. When the implementation admits multiple valid shapes (error handling, abstraction layer, test structure), delegate via the **arena** skill instead so the runners surface the alternatives and the cross-judge guards the pick. Mandatory: no skip-with-reason escape, and Laziness Protocol does not override it (the gain is review separation, not lines saved). A subagent forbidden to spawn satisfies this by owning the diff directly with the same review separation. No "standing by" reply that waits on a nested agent. **Give every file-writing delegate its own worktree** (spawn it with `isolation: "worktree"`, or hand it an exclusive branch), and do not write files or run a suite in a worktree a delegate still holds. On Claude Code, `isolation: "worktree"` branches from the remote default branch unless the `worktree.baseRef` setting is `"head"`. When the delegate builds on commits the default branch lacks, commit them, create its worktree with `git worktree add <path> -b <delegate-branch> HEAD`, and name that base commit in the brief. Fencing a file in the brief's prose is not a lock (**principle-separate-before-serializing-shared-state**). Comments per **Comments**. Surgical edits, re-ground against the source for upstream-derived files. Port shared-primitive improvements to all consumers and verify each. Commit liberally. `skip: this task records and commits existing work; it makes no code change, the session has one active writer, and the user explicitly asked for commits.`
- [x] 5. Verify on the matching surface. "Inconclusive" or wrong-surface is not a pass. Flag it.
- [x] 6. Rebase into small, ordered commits. Stack follow-ups.
- [x] 7. If the design is contested, `interrogate` before shipping. `skip: the commit grouping follows the existing phase structure and no design dispute arose.`
- [x] 8. Run **Opening a PR**. `skip: the user asked for local commits; they did not authorize a pull request.`

## Throughput checkpoint

- Blocking first steps. Inspect tracked and ignored files, then define commit groups before staging.
- Independent workstreams. `n/a: this is one local Git history and staging index; commit order is sequential.`
- Shared mutable state. One writer owns the worktree and index for the full commit sequence.
- Smallest safe decomposition. One agent is the right size because commits must form one ordered history and all files are local.

## Task-specific steps

- [ ] Stage only source, fixtures, plans, and durable evidence in each commit group.
- [ ] Verify the staged file list and whitespace before each commit.
- [ ] Commit the ordered groups and confirm the final history and worktree state.
