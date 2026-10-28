# Synthetic browser checkpoint

**Exit condition.** A browser page served on loopback lets Rick inspect, search, and preview synthetic messages locally without connecting Gmail, sending email, or using a cloud model. It does not implement the production local companion or claim an email gateway exists.

- [x] State the exit condition as a checkable predicate.
- [x] Use the active conversation as the wake mechanism; no external event is being watched and Codex has no `loop` skill.
- [x] Make small units and verify each before continuing.
- [x] Checkpoint each iteration in `.audit/phase1.tsv`.
- [x] Serve the fixture-only UI locally in T3 Preview. Rick can now inspect it in a browser. Phase 1 production-pipeline work remains a separate blocker.

## Evaluation unit completed before this session

- [x] Add a conservative exact canonical fact-claim metric without storing generated text in reports.
- [x] Expand reviewed synthetic examples to 12 messages and rerun detector/model comparisons.
- [x] Fix eligibility so relevance, nonempty source evidence, and both privacy checks must pass.
- [x] Update reports, limitations, and progress.

Evidence: `.audit/phase1-eval-design.md`, `.audit/*-expanded-report.json`, and `scripts/evaluate_qwen.py`.

## Evaluation scorer shape review

- [x] Frame the scorer requirements and rubric.
- [x] Produce two candidates under `/tmp/arena-eval-claims/`.
- [x] Cross-judge both candidates.
- [x] Select the maintainable base, graft useful details, and verify against the fixture corpus.

## Phase 2 design completed

- [x] Define and compare two local data models.
- [x] Record cross-judge results and reconcile gaps.
- [x] Define proposal/review state, dependencies, retention, storage, and release boundary.
- [x] Supersede the earlier Tauri checkpoint after Rick requested a browser UI; preserve a local-only product boundary.

Evidence: `.audit/phase2-data-model.md`, `.audit/phase2-data-model.todo.md`, `/tmp/arena-phase2-data/candidate-a.md`, `candidate-b.md`, and `judge.md`.

## Browser checkpoint completed

- [x] Compare the inbox/detail and digest/drawer layouts in `.audit/browser-layout-options.md`; select inbox/detail so source and evaluation reference remain adjacent.
- [x] Convert the fixture UI to a plain Svelte/Vite browser app and remove the generated Tauri shell.
- [x] Run Svelte check, production build, and dependency audit after the conversion.
- [x] Implement browsing, search, and filters for the 12 synthetic fixtures.
- [x] Keep fixture labels distinct from model output, approved facts, and MCP data.
- [x] Keep Gmail, model inference, persistence, MCP release, and external requests disabled.
- [x] Run the browser UI in the collaborative preview and verify the fixture interactions after the conversion.
- [x] Verify `workshop` search selects one matching fixture and `Expected inspect` returns three matching fixtures in T3 Preview.
- [x] Update browser launch instructions and progress for browser testing.

## Remaining limitations

- [ ] Design and threat review the production local companion API before connecting sensitive browser operations.
- [ ] Continue Phase 1 target-memory/long-thread evaluation and select no model until usefulness and privacy requirements pass.

## Wake and delegation choices

- [x] No recurring wake is needed inside this interactive run.
- [x] One owner implemented the shared UI; architecture candidates and cross-judge were read-only.
