# Phase 2 data model and privacy boundary

Status: reviewed production data/service design. The initial Tauri shell was superseded by Rick's browser UI direction. The synthetic frontend can run in a browser, but no application database, local companion API, sync worker, processing service, or MCP runtime is implemented. Model inference and outbound fact release remain disabled until Phase 1 selects a pipeline and verifies target memory.

## Grounding and choice

The plan requires distinct records for messages, threads, sync checkpoints, jobs, facts, evidence, filter decisions, aliases, policy versions, and digest checkpoints. The current evaluator models synthetic fixtures and expected labels; those expected labels are never product approvals.

Two shapes were compared in `/tmp/arena-phase2-data/candidate-a.md` and `candidate-b.md`, then cross-judged in `/tmp/arena-phase2-data/judge.md`. Candidate A's normalized current-state SQLite scored 18/25; Candidate B scored 20/25. Use A as the smaller base and graft B's dependency tracking, stale-worker fencing, session binding, transactional release/invalidation, and migration rules. Do not add an event journal: no initial product reader needs it, and approval state is already explicit in current rows. Full event sourcing and asynchronous projections add retention and stale-read risks without helping the initial app.

## Records

All IDs are random internal identifiers, not provider IDs. Enable SQLite foreign keys. Store UTC timestamps and use fixed enums/error codes.

| Record | Stored fields and constraints | Boundary purpose |
|---|---|---|
| Account | Internal ID, private account address, enabled state | OAuth refresh credentials stay in the OS credential store. |
| Thread | Account ID, private Gmail thread ID, monotonic context revision, tracked flag, last update, retention deadline; unique by account and provider ID | Keeps related facts and unresolved commitments together. Material message or label changes increment the revision. |
| Message | Account/thread IDs, private Gmail message ID, private sender/subject/labels, received time, language, source revision/hash, in-scope state, retention deadline; unique by account and provider ID | Stores bounded metadata. Full body is fetched locally for processing/review and is not retained as a mailbox copy. |
| Sync checkpoint | Account ID, private Gmail history cursor, import-scope revision, coverage interval, last attempt/success, controlled status | Advance the cursor only after fetched metadata and processing jobs commit. |
| Processing job | Message, source and thread revisions, pipeline version, state, lease expiry, fencing token, attempt count, next-attempt time, fixed error code; unique by input revisions and pipeline | Supports crash recovery and idempotent retries. Bound retry count/backoff; terminal failure remains visible locally and dependent facts stay withheld. A reclaimed job must hold the current fencing token to commit. |
| Filter decision | Message/source revision, relevance (`include`, `deprioritize`, `skip`, `inspect`), reason code, rule version, timestamp | Relevance is independent of privacy and fact approval. |
| Filter override | Account, exact sender/list/thread match, local include/exclude action | User overrides cannot lower privacy rules. |
| Policy version | Immutable policy document/hash, creation time | Active policy changes invalidate disclosure snapshots. |
| Fact | Primary message/thread, deterministic candidate key, type (`summary`, `commitment`, `deadline`, `decision`, `change`, `information`), private text, relevant date, task state (`open`, `resolved`, `superseded`), review state (`proposed`, `approved`, `dismissed`, `stale`), content and approved revisions, source/thread revisions, pipeline version | No persisted `eligible` or `safe` flag. Current eligibility is computed at read time. |
| Fact source | Fact/message IDs, private evidence excerpt or source offsets, source revision/hash, thread revision, evidence validation state; one row per material supporting source | Every supporting source must remain current and in scope. Removing any dependency withdraws the whole fact until a replacement proposal is reviewed. |
| Identity and fact entity | Private normalized identity and kind; fact links with entity role | Original identities remain local and are used only for alias substitution. |
| Disclosure session | Random ID bound to an authenticated local client, created/expiry times, disclosure budget and current usage | Aliases and aggregate disclosure limits are scoped to this session. Validate binding rather than trusting a caller-supplied session identifier. A session expires 24 hours after creation. |
| Session alias | Session ID, private entity ID, generated alias label; unique by session and entity | Create the label once using a cryptographically random local choice from the approved alias vocabulary, then reuse it for that entity throughout the session. Keep the mapping local and never derive aliases from provider IDs. A newly created, removed, or changed mapping increments the session's alias mapping revision. A new session gets independent labels. |
| Source reference | Random opaque token, message ID, disclosure session, source/thread revisions, expiry; unique token | Resolves only to permitted fact output, never raw source. Invalidated on dependency changes. |
| Digest checkpoint | Random ID, session, normalized bounded request, policy/disclosure revisions, ordered fact/revision members, alias mapping revision, expiry, idempotency key | An identical retry returns the same snapshot and aliases without spending budget twice. Any changed dependency invalidates it. Never cache response bodies. |
| Disclosure accounting | Session, idempotent request key, released fact count and bounded disclosure units | Atomic accounting shared by status, digest, search, and source expansion prevents repeated calls from enumerating beyond the aggregate budget. |

Private fact text can be indexed in local SQLite FTS for search. FTS results are candidate IDs only; every result still passes the disclosure boundary. Never expose FTS snippets. Do not copy fixture expected facts into the product store as approved facts.

## Review lifecycle and invalidation

New facts start `proposed`. A local edit changes the content revision and returns the fact to `proposed`; approval is cleared. Approval records the exact revision reviewed in one transaction. Dismissal clears approval. A source, thread context, extraction version, or material evidence change makes the old fact stale for release and creates a new proposal. A changed deadline supersedes its predecessor immediately, even while its replacement awaits review.

Approval is necessary but never sufficient. A release candidate must have a current approved revision, verified evidence from an in-scope source, an `include` relevance decision, supported language, completed processing, no pending invalidation, and no superseding fact. Current policy and privacy checks then decide whether it can leave the app. Detector failure, uncertainty, or missing evidence withholds it.

Processing retries use a unique key over source revision, thread revision, and pipeline version. A worker lease has a fresh fencing token, so a timed-out worker cannot commit after a retry takes ownership. An identical retry reuses current records. A changed input never inherits approval. A material thread update increments its revision and withdraws all dependent facts before reprocessing. Policy updates increment a disclosure revision and invalidate checkpoints atomically. Source deletion or scope removal invalidates dependent facts, FTS entries, tokens, and checkpoints before deleting local source data. Source, account, or scope deletion overrides unresolved-commitment retention. Policy or source changes during selection and serialization cause a fixed `snapshot_expired` response or a fresh render.

## Local storage, retention, and migration

Place the SQLite database in the per-user application data directory with user-only filesystem permissions or a current-user Windows ACL. Keep OAuth credentials in the platform credential store. Ordinary SQLite is not encrypted; do not claim app-level encryption. WAL, temporary files, backups, and caches need the same protection as the main database. Exclude private data from telemetry.

Use the plan's provisional 30-day retention. Retain only the source context needed by unresolved commitments while it remains in scope. Deletion, account removal, or scope removal takes precedence. Re-fetch source text locally when reprocessing is required; if unavailable, withhold dependent facts. Run local cleanup at app startup and at least once every 24 hours while running; purge expired sessions, checkpoints, session aliases, and source tokens in the same transaction. Remove orphan identities. Logical deletion prevents future reads but does not promise forensic secure erasure.

Apply versioned schema migrations locally before services accept reads. Run each migration transactionally, fail closed on error, and rebuild FTS from retained current records. Any migration or policy change that affects disclosure invalidates checkpoints. Backups inherit the same protection and retention rules.

## One disclosure boundary for preview and MCP

The browser preview and MCP adapter call the same `ReleaseService.render` interface with the same request shape and database snapshot. A short serialized disclosure transaction coordinates final validation with policy, source, review, and thread invalidations and atomically reserves the aggregate session budget. It constructs the response before releasing the transaction; no model inference occurs inside it. An idempotency key makes retries repeatable without spending budget twice. MCP cannot query storage directly or call local source-view, account, settings, or review operations.

The renderer accepts only bounded status, digest, search, and opaque-source-reference requests. It reads approved fact candidates from a consistent snapshot, checks current policy and all dependencies, substitutes aliases scoped to a disclosure session, generalizes unnecessary date/amount precision, scans every outgoing text field, and constructs a closed public response DTO. It never copies Gmail IDs, sender/subject, evidence, original identities, source URLs, raw query text, exception details, or message content into output. Fixed error codes and policy-governed coarse counts are used. Aggregate disclosure limits apply across all four tools; detailed withheld reasons remain in the private UI. The renderer rechecks policy, source/thread, review, and disclosure revisions at the serialized release point; a mismatch discards the result.

The renderer is a design boundary, not an implemented or verified guarantee. Tests of the eventual implementation must prove preview/MCP parity and deny stale or private fields.

## Failure behavior

Unprocessed, failed, unsupported-language, policy-invalidated, source-removed, malformed-evidence, or detector-unavailable content stays local. A stale digest checkpoint returns a fixed expiration code. Unknown/removed source references return fixed `not_found`. Logging records only request kind, controlled outcome, counts, and duration.

## Still open

- Target 10 GB total-system memory and long-thread measurements.
- Database encryption decision and verified deletion/backup behavior before live Gmail use.
- Implementation and verification of migrations, aggregate disclosure accounting, renderer, and its preview/MCP parity.

## Browser UI and local companion direction

Rick changed the interface direction from a packaged desktop app to a browser UI. Keep the browser as presentation only. A local companion process must own SQLite, Gmail OAuth credentials, original message access, model inference, privacy checks, and the MCP stdio server. A hosted static UI may serve public assets only; it must not receive messages, credentials, or sanitized/private application API responses. No hosting or deployment has been selected or authorized.

The synthetic checkpoint uses Vite to serve fixtures on loopback and does not exercise the production companion. The concrete design is now in [Local browser API threat design](loopback-http-boundary.md). It specifies one origin, single-use terminal pairing, authenticated expiring sessions, exact Host/origin validation, CSRF protection, CSP, and isolation of private UI operations from MCP. Implementation and security verification remain open before connecting sensitive data. MCP stays on local stdio by default. Only its sanitized interface may later be forwarded through a separately selected and authenticated tunnel.

This direction avoids OS-specific desktop webview and GUI packaging, but it does not eliminate companion builds or platform verification. A local service is still required for the privacy and MCP functions; browser compatibility and companion support targets remain to be selected and tested.
