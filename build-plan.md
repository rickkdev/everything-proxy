# Build plan

Build the read-only Gmail privacy gateway described in [plan.md](plan.md). Complete one phase at a time. Update [progress.md](progress.md) as soon as a phase changes state.

## Working rules

- Work on the first incomplete phase only. If its blocker is recorded and Rick explicitly asks to continue through later phases, continue only with work independent of that blocker. Keep the blocked feature disabled.
- Treat `plan.md` as the product requirements and `build-plan.md` as the execution order.
- Keep changes local and reversible. Do not connect a real Gmail account, send data to a model provider, deploy, publish, or delete user data without explicit authorization for that action.
- Use synthetic fixtures until a phase explicitly requires live-account verification and the user authorizes it.
- Do not claim memory fit, privacy performance, or extraction quality without recording a reproducible measurement.
- Update `progress.md` with the phase status, evidence, blockers, and next unchecked item at the end of each build session.
- If a requirement conflicts with a safety or privacy boundary in `plan.md`, stop that phase, record the conflict, and explain it to Rick.
- Rick authorized a narrow synthetic UI checkpoint after Phase 2 while Phase 1 is blocked. It was initially built as a desktop app; he has since changed the direction to a browser UI. The checkpoint can browse/search fixtures and show clearly labelled evaluation references, but it cannot connect Gmail, invoke models, approve gold labels, or claim production preview/MCP parity. Keep all other dependent implementation behind its phase gate. No public deployment is authorized.

## Phase 1. Evaluate local models and privacy checks

Follow Phase 1 and Phase 2 in `plan.md`.

- [x] Inspect the repository and choose a fixture format and a minimal local evaluation command.
- [x] Create synthetic email fixtures and expected relevance, fact, and disclosure results.
- [x] Compare rules alone, rules with Gretel GLiNER PII small, and rules with OpenAI Privacy Filter.
- [x] Compare Presidio custom patterns with Gretel GLiNER on the shared disclosure fixtures.
- [x] Evaluate Qwen3-4B Q4_K_M for relevance classification and fact extraction.
- [x] Evaluate the pinned Qwen3-1.7B Q8_0 fallback after the 4B candidate missed quality requirements.
- [x] Evaluate Qwen3-4B with rules plus GLiNER and rules plus Privacy Filter at the outgoing fact gate.
- [x] Record quality errors, sampled total RAM, processing time, and model versions in `.audit/` and `progress.md`. Repeat measurements and a synthetic long-thread-shaped input were also run on Rick’s 36 GiB MacBook; see `.audit/phase1-eval-design.md`.
- [x] Record a blocker rather than select a production pipeline: both Qwen sizes scored 3/6 on relevance, and neither detector gate produced an acceptable useful-and-safe fact set. The target is Rick’s 36 GiB MacBook Pro. Standard-corpus repeat runs and one long-context memory sample are recorded; multi-message long-thread behavior and pipeline quality remain open.
- [x] Expand the reviewed fixture set to 12 synthetic messages and rerun the detector profiles. Reports are in `.audit/*-expanded-report.json`.
- [x] Add exact canonical fact-text counts, reject empty evidence, and count a fact as eligible only when relevance is include, evidence is valid, and both privacy checks pass. Reports contain counts only.
- [x] Compare explicit task prompts on both Qwen sizes. Qwen3-4B with prompt v4 reached 10/11 relevance matches but produced no exact canonical fact matches; the 1.7B prompt-v4 run produced no facts. No automatic model pipeline is selected.
- [x] Compare pinned 1-bit Bonsai 1.7B and 1.58-bit Ternary-Bonsai 1.7B on the same fixtures and prompt. Neither candidate passes; reports and limitations are recorded in `.audit/phase1-eval-design.md`.
- [x] Repeatably compare the Qwen3-4B baseline with pinned Qwen3-8B using five alternating pairs, an eligibility-gated exact-fact metric, and the same synthetic corpus/prompt/detector. The larger candidate worsened relevance and privacy outcomes and was rejected; Phase 1 remains blocked. See `.audit/model-quality-trials/summary.json` and `.audit/phase1-eval-design.md`.
- [x] Evaluate Rick-requested Ternary-Bonsai 2 27B MLX on five synthetic corpus passes using the frozen scorer and privacy gates. The checkpoint loads and runs locally, but returns 0/7 eligible exact facts in every pass and is rejected; Phase 1 remains open. See `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx/summary.json` and `.audit/phase1-eval-design.md`.
- [x] Reduce disclosure scope to local proposals. Every proposed fact requires local user approval and a final privacy check before MCP. Synthetic fixture evaluation does not validate target-memory fit.
- [x] Compare two Bonsai 2 prompt changes under the reviewed semantic gate, requiring recovery of the security alert and both changed-date facts while retaining hard disclosure, evidence, and date checks. The gate binds every fact to reviewed supporting evidence, scans returned text including evidence, requires complete case coverage, and rejects non-include/duplicate facts. Prompt `6-security-scope` passed five repeated runs; the broader corpus still does not justify enabling product inference. `.audit/bonsai2-security-review.md`, `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx-security-scope/reviewed-semantic-gate.json`, and `scripts/verify_bonsai2_semantic_gate.py`.
- [x] Expand reviewed synthetic coverage with ordered multi-message thread checkpoints. Require changed and completed facts to replace stale state, bind every claim to its source message, and record per-case gate results plus host/process memory evidence. Three thread cases and six checkpoints pass in five repeated runs; case-level results and cumulative host/process memory evidence are in `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx-threads/`. Product inference stayed disabled and Gmail remained disconnected.
- [x] Broaden the reviewed corpus with longer threads and additional task types before selecting a pipeline. Add explicit expected current facts, stale or resolved facts, evidence, and prohibited disclosures. Screen the pinned local candidate against the expanded set and record per-case outcomes plus target-memory evidence. If the screen fails, retain the blocker and stop candidate selection. If it passes, repeat the expanded run before considering a pipeline. Keep product inference disabled until Phase 1 supports a pipeline. The five-case, 16-checkpoint screen passed 12 checkpoints; it exposed count over-detection, a missed completion, and a stale launch target. No candidate was selected. See `.audit/phase1-eval-design.md` and `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx-expanded-screen/reviewed-thread-semantic-gate.json`.
- [x] Diagnose whether the expanded failures admit a safe local fix without weakening privacy checks or changing reviewed labels. The `84` and `68` registration counts trigger GLiNER's `pin` label; the model omits a completed brief and repeats a launch change after postponement. No safe fix clears all failures under the current labels and privacy gate. See `.audit/phase1-expanded-fix-diagnosis.md`.
- [ ] Resolve the expanded-screen blocker without weakening privacy checks or changing reviewed acceptance labels. Keep product inference disabled until the expanded gate and repeat runs pass.

Acceptance evidence: local evaluation reports with fixtures, commands, model versions, measurements, observed errors, and the blocker. Bonsai 2 prompt `6-security-scope` passes its reviewed message gate. The original `thread-1-current-state` run passes three two-message cases and six checkpoints in five repeats. The expanded five-case screen passes 12 of 16 checkpoints in one run and leaves Phase 1 open. Product inference stays disabled until a pipeline passes the expanded gate and repeat runs.

## Phase 2. Define the local data model and privacy boundary

Follow the data retention, privacy, and storage requirements in Phases 1 and 4 of `plan.md`.

- [x] Define records for messages, threads, sync checkpoints, processing jobs, facts, source references, filter decisions, aliases, and digest checkpoints. Reviewed design: `.audit/phase2-data-model.md`.
- [x] Define the fact-review lifecycle so proposals stay local until approval, and approval never bypasses the final privacy gate. Includes fact revisions and per-source/thread dependencies.
- [x] Define local storage location, OS protections, retention, removal, and database migration approach. SQLite encryption and verified deletion remain open before live use.
- [x] Choose a browser UI backed by a local companion process, preserving local email, model, credential, database, and MCP boundaries. `.audit/phase2-data-model.md` records the direction.
- [x] Threat model and design the loopback HTTP boundary: authenticate every API request; validate Host on all requests; validate Origin/Sec-Fetch-Site for browser requests when present; use CSRF defenses for mutations; prevent DNS rebinding; never put bootstrap secrets in URLs; set a restrictive CSP. `.audit/loopback-http-boundary.md` defines pairing, sessions, route isolation, and implementation acceptance checks. Implementation remains unverified.
- [x] Define one outgoing serializer and privacy check used by both the UI preview and MCP responses, including serialized invalidation checks and aggregate session budgets.
- [x] Define failure states that withhold unprocessed, stale, unsupported-language, malformed-evidence, and policy-invalidated content.

Acceptance evidence: reviewed schema and boundary notes. Raw message content, credentials, and identity mappings remain local by design.

## Phase 2.5. Build the synthetic browser checkpoint

This small checkpoint is independently authorized to make the UI testable in a browser before the model pipeline is selected. It uses only static synthetic fixtures and a local Vite server; it has no production local companion API.

- [x] Show the inbox-and-detail layout and digest-feed layout using synthetic fixtures; choose one. `.audit/browser-layout-options.md` records both.
- [x] Run the synthetic UI in a browser without a desktop wrapper and expose clear cross-platform browser launch instructions. `browser/README.md`; checked in T3 Preview.
- [x] Keep Gmail, model inference, MCP release, persistence, and external network requests disabled.
- [x] Provide browser launch instructions and let Rick try the fixture search, filters, source/reference distinction, and unavailable disclosure preview. `.audit/browser-checkpoint-verification.md`.

Acceptance evidence: a browser page served locally can browse and search fixtures without native OS packaging. The UI clearly distinguishes source content, evaluation references, and unavailable production processing. This is a local demo, not a hosted production app.

Rick requested continued browser readiness on 2026-10-27. Extend this independent checkpoint with the workflows below while keeping the blocked production pipeline disabled.

- [x] Add digest cards, inclusive demo-date filters, explicit withholding reasons, session-only sender correction simulation, and undo. `.audit/browser-ready-results.json`.
- [x] Add labelled offline, empty, and partial-processing scenarios plus setup readiness and narrow-screen navigation. `.audit/browser-ready-verification.md`.
- [x] Verify those workflows in the local browser and record exact production blockers without claiming MCP parity. 17 browser checks pass; desktop and narrow-screen evidence is in `.audit/browser-ready-verification.md`.

## Phase 3. Implement local processing and filtering

Follow Phase 4 of `plan.md` using the pipeline accepted in Phase 1.

- [x] Implement deterministic Gmail metadata and message rules with reasons for each decision. Pure rules and 21 separate synthetic cases are in `scripts/filter_rules.py` and `fixtures/filter-rule-cases.json`; verification is `python scripts/verify_filter_rules.py`.
- [ ] Implement local classification, fact extraction, identifier checks, and alias mapping.
- [x] Implement repeatable message and thread updates, policy-version invalidation, and retention cleanup. `scripts/local_store.py` persists synthetic-compatible metadata; `python scripts/verify_local_store.py` verifies replay, source/thread revision, stale policy/rule rejection, invalidation, expiry, and a two-connection policy update serialized ahead of a stale result check.
- [ ] Verify the synthetic evaluation set against stored results and source evidence.

Acceptance evidence: fixtures produce expected included, deprioritized, skipped, and locally withheld outcomes. Retries produce no duplicate facts.

## Phase 4. Implement Gmail read-only sync

Follow Phase 3 of `plan.md`.

- [ ] Implement local OAuth with the narrowest workable read-only scope and OS credential storage.
- [ ] Implement bounded initial import, metadata-first filtering, incremental Gmail history sync, and manual refresh.
- [ ] Implement resumable processing jobs, reconciliation after expired history, and deletion handling.
- [ ] Confirm the integration has no write operation or broader Gmail scope.

Acceptance evidence: synthetic API responses cover retry, restart, pagination, changed labels, expired history, and removed messages. Live Gmail verification remains gated on explicit authorization.

## Phase 5. Build the browser UI and local companion integration

Follow Phase 5 of `plan.md`.

- [ ] Compare the two proposed layouts using synthetic data and select one.
- [ ] Build the message list, digest, search, filter reasons, corrections, and sync state.
- [ ] Build the preview using the same result serializer and privacy check as MCP.
- [ ] Verify local-only source viewing and safe rendering of untrusted email content.
- [ ] Serve the browser UI from the local companion process and keep Gmail, credentials, database, original messages, and inference on-device.
- [ ] Secure the loopback HTTP interface against cross-origin and DNS-rebinding requests; keep MCP on local stdio.
- [ ] Build and distribute the local companion for supported operating systems. Browser delivery removes the desktop UI package matrix, not the local runtime matrix.

Acceptance evidence: the displayed preview matches the corresponding serialized MCP result for digest and search requests. Review screenshots cover normal, empty, withheld, skipped, and offline states. The browser UI and local companion are verified together on supported operating systems.

## Phase 6. Expose read-only MCP tools

Follow Phase 6 of `plan.md`.

- [ ] Implement `get_status`, `get_digest`, `search_facts`, and `get_source_facts` with bounded results.
- [ ] Return only facts that pass the current disclosure policy.
- [ ] Keep raw messages, local admin routes, Gmail IDs, and identity mappings inaccessible through MCP.
- [ ] Verify retries, stale data, policy changes, malicious email instructions, and denied raw-content requests.

Acceptance evidence: MCP responses match local previews and expose no prohibited fields in results or errors.

## Phase 7. Connect and verify clients

Follow Phase 7 of `plan.md`.

- [ ] Confirm current ChatGPT tunnel access and local Claude Desktop MCP requirements.
- [ ] Connect clients using synthetic data and compare the received result with the local preview.
- [ ] With explicit authorization, run a bounded live Gmail verification without changing mailbox state.
- [ ] Record final memory, freshness, privacy, and coverage limits.

Acceptance evidence: an end-to-end report demonstrates read-only Gmail sync, local processing, exact preview parity, and bounded MCP disclosure.

## Completion

- [ ] Every phase has acceptance evidence linked in `progress.md`.
- [ ] `progress.md` records remaining limitations and the verified model and memory measurements.
- [ ] Documentation explains setup, permissions, retention, model downloads, privacy limits, and disconnect steps.
