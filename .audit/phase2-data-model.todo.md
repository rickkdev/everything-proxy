# Phase 2 data model

## Architect phases

- [x] Ground. Confirmed the product has evaluation scripts but no application database/runtime; mapped the plan's stored entities and read paths in `.audit/phase2-data-model.md`.
- [x] Sketch. Compared current-state normalized SQLite with an event journal/projections in `/tmp/arena-phase2-data/candidate-a.md` and `candidate-b.md`.
- [x] Agree. Cross-judged both in `/tmp/arena-phase2-data/judge.md`; selected A's normalized tables with dependency tracking, worker fencing, session binding, and serialized release constraints from B. Dropped the journal because it has no reader.
- [x] Implement. Wrote `.audit/phase2-data-model.md` as reviewed design only; no database or application code was added.
- [x] Scrap. Cross-judge identified missing dependency invalidation and aggregate disclosure limits. Added these to the selected design before accepting it.

## Current task

- [x] Define records for messages, threads, sync checkpoints, processing jobs, facts, source references, filter decisions, aliases, and digest checkpoints.
- [x] Define the local proposal, approval, edit, dismissal, and withholding lifecycle.
- [x] Keep source text, credentials, aliases, and approval actions local. MCP can read only approved facts that pass current policy.
- [x] Record decisions and the next unchecked Phase 2 task in `progress.md`.

The record lifecycle and disclosure schema are designed. Runtime selection was changed after Rick requested a browser UI. Before implementation, finish the local companion and loopback browser API security design in `.audit/phase2-data-model.md`. Phase 3 remains blocked until Phase 1 model quality and target-memory evidence are resolved.

- [x] Choose browser UI + local companion; keep original mail, credentials, storage, inference, privacy enforcement, and MCP local.
- [ ] Threat model the loopback UI API and complete authentication/bootstrap, origin validation, and CSRF/DNS-rebinding controls before exposing sensitive operations.

## Design acceptance

- [x] Reviewed schema and boundary notes exist in `.audit/phase2-data-model.md`.
- [x] Current implementation work is still disabled; next phase work remains gated by Phase 1 model quality and target-memory evidence.
