# Browser readiness

- [x] `how` over the affected subsystem. Single-agent source inspection per Rick's instructions. `demo.ts` imports gold fixtures, `App.svelte` filters them, and Vite serves only public synthetic assets. No service boundary exists.
- [x] `architect` for parallel design exploration. skip: Rick requests one agent for work one agent can finish. Compare shapes sequentially in `browser-ready-design.md`.
- [x] Write the throughput checkpoint as four todo items.
  - [x] **Blocking first steps.** Record Phase 1 blocker and finish loopback threat design before expanding the independent synthetic checkpoint.
  - [x] **Independent workstreams.** n/a: one coupled browser feature, one owner.
  - [x] **Shared mutable state.** Session-only Svelte state. No database, background jobs, or parallel writers.
  - [x] **Smallest safe decomposition.** One worker keeps fixture semantics and UI copy consistent. Design, implement, verify.
- [x] Delegate code-writing to a subagent using your configured feature model. skip: Rick's one-agent instruction overrides delegation. Own the diff directly.
- [x] Verify on the matching surface.
- [x] Rebase into small, ordered commits. Stack follow-ups. skip: all project files are untracked; preserve the current checkout and do not create a commit or PR.
- [x] If the design is contested, `interrogate` before shipping. skip: no contested design or shipping.
- [x] Run **Opening a PR**. skip: PR operations are unauthorized.
- [x] Update progress and record evidence.
