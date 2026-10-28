# Phase 1 session checklist

## Feature playbook

- [x] `how` over the affected subsystem. The repository has no implementation modules yet. `README.md` only names the project, so there is no existing subsystem flow to explain.
- [x] `architect` for parallel design exploration. skip: the fixture task adds static synthetic data and defines no application types, functions, or module boundaries.
- [x] Write the throughput checkpoint as four todo items. A dimension that genuinely does not apply (single file, no fan-out) keeps its item with `n/a: <reason>` rather than being dropped:
  - **Blocking first steps.** Inspect repository shape and choose the fixture and runner conventions before adding evaluation data.
  - **Independent workstreams.** n/a: the phase uses one ordered evaluation pipeline with shared fixtures, scorer, and local model lifecycle.
  - **Shared mutable state.** n/a: no parallel workers or shared edits are planned.
  - **Smallest safe decomposition.** Keep fixtures in one JSON document, shared detector scoring in `evaluate.py`, Qwen scoring in `evaluate_qwen.py`, and downloads in `download_models.py`.
- [ ] Delegate code-writing to a subagent using your configured feature model (default in poteto-mode's Models section) with a specific scope (file paths, named data shape and its organizing structure per **principle-model-the-domain**, a state machine over scattered booleans, a table/registry over branching, a typed model over repeated shape assumptions, chosen before the delegate writes logic, and success criteria). Pick each subagent's reasoning level for the job, per the Subagents section. When the implementation admits multiple valid shapes (error handling, abstraction layer, test structure), delegate via the **arena** skill instead so the runners surface the alternatives and the cross-judge guards the pick. Mandatory: no skip-with-reason escape, and Laziness Protocol does not override it (the gain is review separation, not lines saved). A subagent forbidden to spawn satisfies this by owning the diff directly with the same review separation. No "standing by" reply that waits on a nested agent. **Give every file-writing delegate its own worktree** (spawn it with `isolation: "worktree"`, or hand it an exclusive branch), and do not write files or run a suite in a worktree a delegate still holds. On Claude Code, `isolation: "worktree"` branches from the remote default branch unless the `worktree.baseRef` setting is "head". When the implementation admits multiple valid shapes, delegate via arena. Comments per **Comments**. Surgical edits, re-ground against the source for upstream-derived files. Port shared-primitive improvements to all consumers and verify each. Commit liberally. **skip: global and repository instructions favor one owner for this sequential task; no independent parallel workstream exists.**
- [x] Verify on the matching surface. "Inconclusive" or wrong-surface is not a pass. Flag it. The JSON parser accepted the fixture file, and a structural check confirmed seven records with required expected fields.
- [x] Rebase into small, ordered commits. Stack follow-ups. **skip: the fixture is a single data-only unit, and no commit was requested.**
  Use the **sequence-verifiable-units** principle, building, verifying, and committing each small unit before the next.
- [ ] If the design is contested, `interrogate` before shipping. **skip: the fixture format choice is documented and no implementation is being shipped.**
- [x] Run **Opening a PR**. **skip: the user requested Phase 1 work, not a pull request.**

## Current repository task

- [x] Inspect the repository and choose a fixture format and a minimal local evaluation command.
- [x] Create synthetic email fixtures and expected relevance, fact, and disclosure results.
- [x] Compare rules alone, rules with Gretel GLiNER PII small, and rules with OpenAI Privacy Filter.
  - [x] Define the shared message, expected disclosure, detected span, and report shapes before implementation.
  - [x] Compare evaluator designs. Keep one runner and scorer with local model adapters so every candidate uses identical fixtures and metrics.
  - [x] Implement the rules baseline, local-only model adapters, and combined profiles.
  - [x] Run all candidate profiles on the synthetic fixture set and record errors and measurements. The rules profile covered 26 of 39 expected spans. Rules plus GLiNER covered 27 with 8 extras. Rules plus Privacy Filter covered 33 with 31 extras. Results are exploratory because the corpus has seven messages and the host has 36 GiB RAM.
- [x] Compare Presidio custom patterns with GLiNER and the rules baseline. Presidio covered 27 of 39 spans with 5 extras; it did not justify selection.
- [x] Evaluate Qwen3-4B Q4_K_M and the Qwen3-1.7B Q8_0 fallback for relevance and evidence-grounded fact extraction.
- [x] Compare Qwen fact output behind rules plus GLiNER and rules plus Privacy Filter.
- [x] Record quality errors, sampled memory, processing time, and model versions in `.audit/` and `progress.md`.
- [x] Record the concrete blocker: neither model/detector pipeline met usefulness and disclosure checks, and the 10 GB target was not measured on matching hardware.

## Evidence

- [x] Repository inventory and runtime inspection.
- [x] Current host inspection. macOS arm64 reports 36 GiB RAM and 40 GiB free disk, so it does not match the 10 GB target assumption.
- [x] Checkpoint before fan-out.
- [x] Fixture acceptance evidence in `fixtures/email-evaluation.json` and JSON/structure validation.
- [x] Acceptance evidence exists for the evaluations and blocker in `.audit/` and `progress.md`.
