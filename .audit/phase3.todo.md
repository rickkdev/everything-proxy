# Phase 3 task: deterministic message rules

- [x] 1. `how` over the affected subsystem.
- [x] 2. `architect` for parallel design exploration.
- [x] 3. Write the throughput checkpoint as four todo items. A dimension that genuinely does not apply (single file, no fan-out) keeps its item with `n/a: <reason>` rather than being dropped:
  - Blocking first steps. Gates run before fan-out.
  - Independent workstreams. Disjoint files, services, or layers parallelize. Shared writes serialize.
  - Shared mutable state. Default to splitting the target (the `principle-separate-before-serializing-shared-state` principle skill). Serialize only for real invariants.
  - Smallest safe decomposition. If one worker is best, name why.
- [ ] 4. Delegate code-writing to a subagent using your configured feature model (default in poteto-mode's Models section) with a specific scope (file paths, named data shape and its organizing structure per `principle-model-the-domain`, a state machine over scattered booleans, a table/registry over branching, a typed model over repeated shape assumptions, chosen before the delegate writes logic, and success criteria). Pick each subagent's reasoning level for the job, per the Subagents section of poteto-mode. When the implementation admits multiple valid shapes (error handling, abstraction layer, test structure), delegate via the `arena` skill instead so the runners surface the alternatives and the cross-judge guards the pick. Mandatory: no skip-with-reason escape, and Laziness Protocol does not override it (the gain is review separation, not lines saved). A subagent forbidden to spawn satisfies this by owning the diff directly with the same review separation. No "standing by" reply that waits on a nested agent. Give every file-writing delegate its own worktree (spawn it with `isolation: "worktree"`, or hand it an exclusive branch), and do not write files or run a suite in a worktree a delegate still holds. On Claude Code, `isolation: "worktree"` branches from the remote default branch unless the `worktree.baseRef` setting is `"head"`. When the delegate builds on commits the default branch lacks, commit them, create its worktree with `git worktree add <path> -b <delegate-branch> HEAD`, and name that base commit in the brief. Fencing a file in the brief's prose is not a lock (`principle-separate-before-serializing-shared-state`). Comments per `Comments`. Surgical edits, re-ground against the source for upstream-derived files. Port shared-primitive improvements to all consumers and verify each. Commit liberally. `skip: repository instructions require one engineer for initial implementation; design work received two independent candidates and a cross-judge, while the implementation stayed with the primary engineer.`
- [x] 5. Verify on the matching surface. "Inconclusive" or wrong-surface is not a pass. Flag it.
- [ ] 6. Rebase into small, ordered commits. Stack follow-ups. Use the `sequence-verifiable-units` principle, building, verifying, and committing each small unit before the next. `skip: the checkout has no committed project baseline and its project files are untracked, so there is no safe base for a rebase or scoped commit.`
- [x] 7. If the design is contested, `interrogate` before shipping. `skip: the cross-judge resolved the candidate differences; no unresolved design dispute remains.`
- [ ] 8. Run `Opening a PR`. `skip: project instructions prohibit pull request operations unless Rick explicitly authorizes them.`

## Architect phases

- [x] Ground. Read the build and progress records, fixture schema, and existing evaluator.
- [x] Sketch. Collect two structurally distinct filter designs.
- [x] Agree. Use the cross-judge result to select an ordered pure evaluator with relevance and privacy holds separated.
- [x] Implement. Follow the agreed decision shape in the filter module.
- [x] Scrap. Keep the sketch because implementation matched its ownership and decision boundaries.

## Arena phases

- [x] Frame. Grade designs on boundary clarity, privacy fit, ambiguity handling, interface size, and synthetic verifiability.
- [x] Fan out. Two read-only candidates wrote to separate `/tmp/arena-phase3-rules/` files.
- [x] Cross-judge. A distinct model family compared the candidates against the rubric.
- [x] Pick a base. Candidate B scored 21/25 versus Candidate A's 17/25.
- [x] Graft. Keep B's privacy boundary and precedence, with A's typed result and simpler ordered evaluator.
- [x] Verify. Replay synthetic rule cases against the implementation.

## Throughput checkpoint

- [x] Blocking first steps: inspect the fixture schema, filter evaluator, and phase 1 blocker before selecting deterministic rules.
- [x] Independent workstreams: n/a, one narrow policy module and one fixture-based verification path share the same rule contract.
- [x] Shared mutable state: n/a, no concurrent writers; the current checkout is entirely untracked, so worktree-based delegation cannot preserve its state.
- [x] Smallest safe decomposition: one engineer owns the feature because the repository explicitly specifies one engineer for initial implementation and all work is gated by one local rule contract.

## Task

- [x] Define the metadata/message input shape and rule decision shape.
- [x] Implement the first incomplete Phase 3 task only, if independent of Phase 1's model-selection blocker.
- [x] Verify against synthetic fixtures and record evidence, limits, and next task in `progress.md`.
