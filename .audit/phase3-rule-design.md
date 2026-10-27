# Phase 3 deterministic filter design

## Usage and ownership

The local processing caller passes normalized private Gmail metadata, an optional fetched body, and local rule configuration to a pure filter. It receives a relevance decision, a stable reason code, a rule version, a body-fetch instruction, and an independent privacy hold. The filter does not access Gmail, storage, model inference, approvals, aliases, or MCP.

```python
decision = evaluate_metadata(metadata, rules)
decision = evaluate_message(metadata, body, rules, prior=decision)
```

The input is a frozen `MessageMetadata` record with exact sender and list identities, Gmail labels, subject, thread-tracking and starring signals, and optional language. `RuleSet` owns exact user overrides, selected identities, low-value sender/list identities, and supported languages. `FilterDecision` carries a relevance enum, reason enum, rule version, `fetch_body`, and an optional independent `PrivacyHold`.

## Synthesis decision

Candidate B is the base because it makes relevance independent from privacy withholding and rejects using evaluation labels as runtime data. Candidate A contributes the concrete decision fields, the metadata/body split, and first-match precedence. The cross-judge preferred B at 21/25 over A at 17/25, and recommended exact configured identities before routine-message suppression.

The implementation uses one ordered pure module instead of separate metadata and message modules. This keeps the public surface to two caller functions while making the metadata-first decision explicit. Rules default to conservative `inspect`. Spam, trash, drafts, and exact local exclusions can skip before body fetch. A user include can override heuristic noise rules but cannot override protected Gmail labels. Promotions require the Gmail promotion label. Newsletters require an exact configured list ID. Receipts and shipments require an exact configured sender and a narrow subject pattern. Unsubscribe and no-reply alone do not cause a skip.

Privacy holds remain separate fields. Unsupported or unknown language and sensitive content can withhold processing while relevance remains independently classified. A relevance decision never approves facts or permits disclosure.

## Rejected choices

- A free-form evidence reducer was not selected because it obscures which rule wins and complicates stable reason behavior.
- Fixture expected relevance was not selected as filter input because those labels are evaluation targets, not production metadata.
- Broad subject-only exclusions were rejected because they could suppress useful requests or security alerts.
- A new service, database, or persistence layer was rejected because those integration tasks follow this deterministic rule task.

## Verification contract

Separate synthetic rule cases supply labels, exact identities, overrides, and message text. The verifier checks outcome, reason code, body-fetch choice, and privacy hold. The 12 model-evaluation fixture labels remain separate and are not treated as proof of filter accuracy.
