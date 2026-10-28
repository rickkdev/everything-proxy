# Build the local Gmail privacy gateway

Create a browser-based interface for a local Gmail privacy gateway. A local companion process owns Gmail access, credentials, original messages, database, model processing, privacy checks, and MCP. The browser UI previews the exact information ChatGPT or Claude can receive. Do not send original email or credentials to a hosted service.

Design for Rick’s current MacBook Pro target: macOS arm64 with 36 GiB installed unified memory, without a dedicated GPU. This is the current hardware target; reassess if the target machine changes. Do not send original email to a cloud service for classification, extraction, embeddings, or privacy checks.

## Use this plan

Implement the phases in order. Check a box only after its evidence exists. This plan authorizes no implementation, account connection, deployment, or pull request operation by itself.

Use one engineer for the initial implementation. Add parallel work only when independent work justifies it. Keep verification proportional to the change and use synthetic email fixtures before connecting Gmail.

Rick first authorized a synthetic desktop checkpoint, then changed the direction to a browser UI so the interface does not need separate Windows and Linux desktop packages. The checkpoint remains independent while Phase 1 is unresolved: it may browse/search synthetic fixtures and show evaluation references as test data. It must not connect Gmail, invoke a model, approve fixture gold labels, or claim its preview is a verified MCP disclosure. It runs locally in a browser; no deployment or public hosting is authorized.

Rick's 2026-10-27 request extends browser checkpoint readiness to digest cards, demo-date filtering, explicit withheld reasons, session-only sender-filter simulation, setup status, responsive navigation, and labelled offline, partial, and empty scenarios. These are synthetic browser interactions, not production processing, persisted rules, fact approvals, or disclosure.

On 2026-10-28 Rick asked for the product to be ready for testing with his own Gmail and Bonsai 2. Bonsai 2 is therefore enabled as a local, proposal-only extraction pipeline for personal testing despite the open Phase 1 expanded gate. Approval of each fact and the final privacy check remain mandatory before any MCP release; English-only processing, local-only originals, and `gmail.readonly` are unchanged.

Throughput checkpoint for this planning task is not applicable. Local model reports now contain single-run throughput and memory samples. Treat them as exploratory measurements, not a performance baseline. Measure repeatability and target-device fit before choosing a production pipeline.

## Preserve the product boundaries

- [ ] Support Gmail only in the first version.
- [ ] Request `gmail.readonly`. Expose no sending, drafting, deletion, labeling, archiving, or mark-as-read capability.
- [ ] Support summaries, commitments, deadlines, decisions, changes, and information relevant to a question.
- [ ] Return task facts by default. Replace people and organizations with aliases.
- [ ] Keep model-generated facts local as proposals until the user approves each fact in the local browser UI. Approval never bypasses sensitivity rules or the final privacy check.
- [ ] Keep Gmail credentials, original content, identity mappings, and processing inside the local trust boundary.
- [ ] Exclude attachments, OCR, remote images, and link following initially. Report these coverage limits.
- [ ] Let only local settings change privacy policy or expand mailbox access. A model tool call cannot lower protections.
- [ ] Explain that aliases reduce exposure but do not guarantee anonymity. Context can identify someone or reveal confidential information.

## Phase 1. Define representative tasks and privacy rules

- [ ] Create synthetic messages covering direct requests, newsletters, receipts, security alerts, changed deadlines, and sensitive correspondence.
- [ ] Include English and any additional languages selected for support. Treat unsupported language or extraction failures as withheld content.
- [ ] Write expected facts, inclusion decisions, and prohibited disclosures for each fixture.
- [ ] Define independent relevance and disclosure decisions. An important email can still be restricted to local viewing.
- [ ] Start with these editable privacy defaults.
  - Never disclose credentials, authentication links, recovery codes, or access tokens.
  - Alias people, organizations, domains, and identifying project names.
  - Preserve dates and amounts only when necessary for the task. Generalize unnecessary precision.
  - Hold medical, intimate, and other configured sensitive topics locally for review.
  - Strip signatures, tracking URLs, routing headers, and repeated quoted text from outgoing facts.
- [ ] Choose a provisional retention window of 30 days for processed messages. Keep unresolved commitments within that window's threads until resolved or explicitly expired.
- [ ] Define how a user expands history locally. Report search coverage instead of implying that a recent import covers the entire mailbox.

Acceptance evidence is a reviewed fixture set with explicit expected behavior. No model quality claim is valid before evaluation.

## Phase 2. Compare local processing options under the memory budget

- [ ] Start with Qwen3-4B Q4_K_M through `llama.cpp` for local relevance classification and structured fact extraction in one pass.
- [x] If the 4B candidate fails quality or the memory target, compare Qwen3-1.7B Q8_0 as a lower-memory fallback before changing supported scope.
- [x] Start with Gretel GLiNER PII small plus deterministic rules for identifier detection. Treat it as a candidate detector, not a privacy guarantee.
- [x] Keep OpenAI Privacy Filter as a comparison candidate for identifier detection. Do not use a generative model as the sole privacy check.
- [x] Compare rules plus a small PII detector with the same pipeline plus a small quantized language model for fact extraction.
- [x] Compare Presidio custom patterns with the proposed GLiNER detector. Presidio's small fixture gain did not justify selecting it.
- [x] Record Qwen3-4B Q4_K_M's model file size as a download-size reference only and measure total process and system memory on the MacBook target. Model reports record the file size, host RAM, process RSS, and sampled total-system use.
- [x] Run inference locally with pinned model versions. Evaluators call only the loopback server; no external model service is used.
- [x] Process one bounded message or thread segment at a time. Reuse a worker process and limit context, output length, and batch size.
- [ ] Preserve source evidence for each extracted fact. Reject malformed output and unsupported claims. Do not interpret a model's confidence as a privacy guarantee.
- [x] Check extracted facts for identifiers and restricted context before making them eligible for MCP. Neither detector pipeline passed the synthetic leakage-and-utility check.
- [x] Measure missed private spans, sensitive-topic leakage, missed important messages, unsupported facts, and useful task completion on the reviewed synthetic corpus.
- [x] Record cold start, warm processing time, messages per minute, peak total memory, and synthetic long-thread behavior on the MacBook target. Repeated Bonsai v4 runs and a 5,081-character synthetic thread-shaped input are recorded in `.audit/phase1-eval-design.md`; quality still fails.
- [ ] Select a pipeline only if it fits within the MacBook’s 36 GiB total RAM with room for the OS, UI, database, and MCP server. Avoid relying on heavy swapping.
- [ ] If no candidate meets both memory and quality requirements, reduce model size or supported scope. Never silently fall back to cloud processing or raw-text disclosure.

Acceptance evidence is a reproducible local evaluation with model versions, hardware, inputs, measurements, and observed errors. Set latency targets from these results before building automatic refresh behavior around them.

## Phase 3. Import Gmail and synchronize changes

- [ ] Build the local OAuth flow. Keep refresh tokens in the OS credential store and redact credentials from logs.
- [ ] Import a configurable recent window, initially 30 days. Include eligible archived received mail so inbox placement does not decide relevance.
- [ ] Fetch metadata first. Use Gmail search for date scope and explicit exclusions. Fetch bodies only after metadata rules select them.
- [ ] Store a Gmail history checkpoint for incremental updates. Start with polling every five minutes while the app runs and a manual refresh action.
- [ ] Handle new messages, deleted messages, label changes, pagination, rate limits, offline periods, and token expiry.
- [ ] Reconcile the configured scope if Gmail rejects an expired history checkpoint.
- [ ] Store retrieved work durably before advancing its sync checkpoint. Track processing completion separately so model failures cannot lose messages.
- [ ] Make retries update existing records by account and Gmail message ID. Prevent duplicate facts and concurrent refresh jobs.
- [ ] When source messages leave the allowed scope or are deleted, remove their eligible facts, search entries, and cached previews locally. Recompute affected thread state.
- [ ] Display last successful sync, import coverage, pending processing, failures, and offline status.

Acceptance evidence includes restart during import, duplicate history events, expired history, deletion, and recovery from offline operation against fixtures. A live Gmail check requires explicit account authorization and must leave the mailbox unchanged.

## Phase 4. Filter noise and store searchable facts

- [ ] Use a local SQLite database and built-in full-text search initially. Add local semantic search only if measured retrieval failures justify it.
- [ ] Keep messages, processing jobs, facts, source references, filter decisions, identity mappings, policy versions, and digest checkpoints as separate records.
- [ ] Keep any temporary original-content cache bounded and protected. Avoid permanently duplicating the mailbox. Re-fetch source text locally when reprocessing requires it.
- [ ] Store filter decisions as include, deprioritize, skip, or inspect further. Record the reason and rule version.
- [ ] Apply explicit user exclusions first. Give explicit includes priority over heuristic noise filters, while preserving privacy restrictions.
- [ ] Skip spam, trash, and drafts by default. Deprioritize promotions, newsletters, and routine automated notifications.
- [ ] Use exact sender and mailing-list matches, Gmail labels, and targeted subject patterns before model inference.
- [ ] Treat unsubscribe headers and `no-reply` senders as signals. Never exclude them automatically on that basis alone.
- [ ] Prioritize direct requests, selected senders, starred messages, tracked threads, failures, cancellations, and security alerts.
- [ ] Inspect uncertain messages locally rather than silently rejecting them based on the subject.
- [ ] Classify and extract facts in the same local model pass when inference is needed.
- [ ] Store facts with type, relevant dates, internal entity references, source message, evidence, and status such as open, resolved, or superseded.
- [ ] Revisit affected thread facts when new messages change deadlines or resolve requests. Retain only the context needed for accurate interpretation.
- [ ] Invalidate affected decisions and outbound caches when rules, privacy policy, model version, or source context changes.

Acceptance evidence includes finding a useful automated alert, suppressing a newsletter, recovering a mistakenly skipped sender, and replacing a superseded deadline without duplicating it.

## Phase 5. Build the browser UI and local companion integration

- [ ] Show two lightweight layout alternatives using synthetic data before implementing substantial UI components.
  - Option A uses an inbox list on the left and a selected message's facts and MCP preview on the right.
  - Option B uses a digest feed with expandable source cards and an MCP preview drawer.
- [ ] Use Option A as the working default unless the review favors Option B.
- [ ] Include navigation for digest, processed messages, deprioritized messages, skipped messages, and locally withheld messages.
- [ ] Show each processed message's aliased sender, sanitized subject or generated title, date, facts, and processing status.
- [ ] Display why a message was included or skipped. Allow local sender and mailing-list overrides, followed by reprocessing.
- [ ] Support search, date range, relevance filters, refresh, and sync progress. Keep configuration small.
- [ ] Include a local original-message view or an action to open Gmail. Clearly distinguish private source viewing from information eligible for MCP.
- [ ] Add an MCP preview for a selected message, digest, or search request. Show the exact structured result and text fields the tool would return.
- [ ] Let the user approve, edit, or dismiss each proposed fact locally. Re-run the final privacy check after edits.
- [ ] Generate previews and real tool responses through the same serializer and privacy gate. Preview must not be an approximate UI summary.
- [ ] Show policy version, coverage, last sync, pending work, truncation, withheld content, and the reason for withholding.
- [ ] Use aliases consistently within a preview session. Keep original identity lookup local. Warn that copying original information into cloud chat bypasses the proxy.
- [ ] Render email as untrusted text. Do not execute HTML, load remote resources, or turn email instructions into app actions.
- [ ] Serve the UI in a supported browser from a local companion process. Keep app data, model inference, and local services on the user's device; do not require a hosted service to view or process email.
- [ ] Bind any local HTTP interface to loopback only. Authenticate every API request; validate Host on every request and Origin/Sec-Fetch-Site on browser requests when present; protect mutations against CSRF; prevent DNS rebinding; and never put bootstrap secrets in URLs. Expose only the UI API. MCP defaults to local stdio; only its sanitized interface may later be forwarded through an explicitly selected and authenticated tunnel. Never make raw email available over MCP.
- [ ] Document browser compatibility and distribute the local companion for supported operating systems. A browser UI removes desktop webview packaging, but the local companion still needs platform builds.

Acceptance evidence includes screenshots of both alternatives and the chosen layout, plus browser UI and local companion verification on supported operating systems. Demonstrate digest, search, skipped-message correction, withheld content, empty inbox, offline state, and partial processing. Verify that the preview equals an actual MCP tool result for the same request and snapshot.

## Phase 6. Serve bounded read-only MCP tools

- [ ] Keep the MCP listener separate from local admin and original-content routes. Use local stdio by default; expose only the sanitized tool interface if a remote transport is separately selected and authenticated.
- [ ] Implement a minimal proposed tool set.
  - `get_status` returns sanitized sync health, coverage, and processing backlog.
  - `get_digest` returns eligible facts and changes for an explicit interval or prior digest checkpoint.
  - `search_facts` returns bounded facts relevant to a question, with optional dates and fact types.
  - `get_source_facts` expands an opaque source reference into eligible facts, never original email text.
- [ ] Refresh stale local data within an evaluated time budget. If work remains, return an honest snapshot with pending counts and a retry indication.
- [ ] Apply current disclosure policy and request-scoped aliases immediately before serialization. Check every outgoing text field, including errors and titles.
- [ ] Scope aliases consistently across related tool calls. Avoid exposing globally stable identity aliases across unrelated sessions by default.
- [ ] Return opaque source references. Keep Gmail IDs, real addresses, raw subjects, and private source URLs inside the local application.
- [ ] Return only locally approved facts. A tool call cannot approve, edit, or release a proposed fact.
- [ ] Bound result size, time range, pagination, and aggregate disclosure. Reject attempts to fetch arbitrary files, URLs, raw messages, or restricted content.
- [ ] Treat all email content as data. Email instructions cannot change rules or request extra retrieval.
- [ ] Make digest checkpoints explicit and repeatable. Reading a digest never changes Gmail unread status. A retry returns the same digest snapshot while valid under current policy.
- [ ] Record minimal local disclosure metadata without storing raw response bodies or credentials in routine logs.

Acceptance evidence includes tool calls that match the UI preview, stable retries, policy changes between calls, expired snapshots, malicious email instructions, and attempts to request original content.

## Phase 7. Connect private clients and verify the complete flow

- [ ] Verify current ChatGPT custom MCP and Secure MCP Tunnel availability for Rick's account before selecting that transport.
- [ ] Connect ChatGPT through Secure MCP Tunnel where available. Keep local admin and original-content services outside the forwarded MCP interface.
- [ ] Support local MCP transport for Claude Desktop. Treat a Claude web connection as a separate authenticated remote transport decision.
- [ ] Keep transport credentials distinct from Gmail credentials. Document disconnect and revocation.
- [ ] Test with synthetic data first. Compare the exact response leaving the gateway with the local preview.
- [ ] With explicit account authorization, verify a bounded Gmail sample through sync, filtering, fact extraction, UI preview, and a real client request.
- [ ] Demonstrate a new message, changed deadline, resolved request, excluded sender, sensitive email, and recovery after restart.
- [ ] Measure peak system memory and end-to-end freshness under representative backlog. Publish supported operating conditions and observed limits.
- [ ] Document installation, model downloads, local storage, retention, refresh behavior, privacy limits, and account revocation.

Done means the local interface and MCP return the same permitted facts, Gmail remains unchanged, failures withhold unprocessed content, and the measured system fits the agreed memory budget.

## Record unresolved decisions

- Target CPU, supported browsers, companion operating systems, and supported languages remain unknown.
- The browser UI may be distributed as static assets, but no hosting provider or public deployment is selected. Sensitive API calls must stay on the local companion.
- The local model and exact memory allocation depend on Phase 2 measurements.
- Model output is a local proposal only. The current small-corpus evaluations do not justify automatic fact disclosure.
- Thirty days of history and five-minute polling are proposed defaults, not confirmed preferences.
- The synthetic checkpoint compared both inbox layouts and selected inbox/detail. Production responsive behavior and final layout refinement still need user feedback.
- ChatGPT plan and tunnel access remain unverified.
- Public distribution and Google's verification requirements require a separate assessment before release beyond personal use.
- Extraction may omit important context or invent facts. Source checks and measured evaluation reduce risk but do not eliminate it.
- Changing local privacy policy cannot retract information already disclosed to a model provider.

## Apply the planning principles

Boundary Discipline places the final disclosure check before serialization and separates the private UI from MCP access. Make Operations Idempotent makes retries converge without duplicate facts. Sequence Work into Verifiable Units puts local privacy and memory evaluation before live account integration.

## Read the primary references

- [Gmail sync](https://developers.google.com/workspace/gmail/api/guides/sync).
- [Gmail read-only permissions](https://developers.google.com/workspace/gmail/api/auth/scopes).
- [Gmail search and filtering](https://developers.google.com/workspace/gmail/api/guides/filtering).
- [Gmail metadata retrieval](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get).
- [Gmail labels](https://developers.google.com/workspace/gmail/api/guides/labels).
- [Presidio limitations](https://github.com/data-privacy-stack/presidio/blob/main/docs/faq.md).
- [GLiNER PII model overview](https://docs.api.nvidia.com/nim/reference/nvidia-gliner-pii).
- [OpenAI Privacy Filter model card](https://huggingface.co/openai/privacy-filter).
- [Qwen3-4B quantized weights](https://huggingface.co/Qwen/Qwen3-4B-GGUF).
- [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
- [Claude local MCP](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).
