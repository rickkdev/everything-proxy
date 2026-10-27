# Repository instructions

## Continue the email privacy gateway build

At the start of every build session, read `plan.md`, `build-plan.md`, and `progress.md`.

Use `plan.md` for product scope, privacy rules, and acceptance requirements. Use `build-plan.md` for the ordered work. Use `progress.md` as the source of truth for completed work, evidence, blockers, and the next task.

Find the first incomplete phase in `build-plan.md`, then continue its first unchecked task. Finish and verify that task before moving to the next task. Do not skip ahead because a later task looks easier. If a task is blocked, record the concrete blocker and evidence in `progress.md`, then continue only with independent work in the same phase.

At the end of every build session, update `progress.md` with the work completed, evidence, decisions, blockers, and the next unchecked task. Check off a task only when its acceptance evidence exists. Keep `plan.md` and `build-plan.md` current when an approved scope change changes the requirements or sequence.

Use synthetic email fixtures until a task requires live Gmail verification. Never broaden Gmail permissions, send email, expose raw email to a model provider, deploy, or publish without explicit user authorization. Keep original email, credentials, and alias mappings local. Apply the disclosure rules in `plan.md` to every MCP response.
