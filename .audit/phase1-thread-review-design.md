# Phase 1 thread evaluation design

## Grounding

The current model gate owns one output per synthetic message. `score_output` ties fact evidence to that message's source text, and `score_run` requires exact coverage of the 11 English fixtures. The gate hardcodes useful-fact and relevance thresholds plus security and date cases. The loader discards each fixture's existing `thread_id`. `macbook-long-thread.json` is one long message body, so it does not test messages arriving over time or facts being updated and resolved.

## Candidate A: ordered thread checkpoints

Keep `email-evaluation.json` and its message gate unchanged. Add `thread-evaluation.json` with `thread_cases`, each holding ordered source messages and checkpoints. A checkpoint names the last message visible and specifies current expected relevance, reviewed facts, absent/superseded facts, and prohibited disclosures. Each inference request receives the whole prefix as one ordered thread. Each output is keyed by case and checkpoint. Evidence refers to one or more message IDs and exact source quotes. Review labels bind output fact plus evidence references to expected thread fact IDs.

This measures thread interpretation, date replacement, request resolution, and privacy context that appears in an earlier message. It yields a per-checkpoint result and does not reinterpret message-level outputs as thread results.

## Candidate B: evaluate each message then assemble thread state

Keep the existing single-message prompt and output shape. Add thread membership and reviewed expected outcomes, then evaluate messages independently and let the scorer derive the final thread state from their facts. Evidence remains tied to a single message. This uses the existing model request contract and can report per-message results inside a thread.

This measures message extraction with grouped reporting, but it cannot establish whether the model uses earlier messages when interpreting a later update or whether a later message resolves an earlier commitment.

## Rubric

1. Must run inference on multiple messages together in chronological order.
2. Must represent state at more than one point where updates or resolution matter.
3. Must bind claims to exact evidence in identified source messages.
4. Must fail closed on missing/reordered messages, unreviewed claims, unsupported evidence, prohibited disclosures, stale facts, and incomplete coverage.
5. Must report each checkpoint outcome and the scope of memory samples.
6. Must leave existing single-message gate, product inference setting, and Gmail boundary unchanged.

## Synthesis decision

Choose Candidate A. Candidate B preserves more of the old runner, but its per-message requests cannot evaluate cross-message interpretation. Candidate A owns a smaller, explicit thread dataset and a separate deterministic gate, while leaving the existing baseline schema and reports unchanged. Use ordered messages plus visible-prefix checkpoints as the domain shape. An evaluator sends one bounded thread prefix per checkpoint. The scorer checks exact coverage, chronological source order, message-level output schema, reviewed output/evidence labels, evidence source IDs and substrings, prohibited text, and expected current facts. A checkpoint can also require prior facts to be absent after an update or resolution.

Independent design readers converged on ordered messages, explicit expected outcomes, source attribution, full case coverage, and separate gate thresholds. Candidate A additionally represents checkpoints; Candidate B's independent-message model does not satisfy criteria 1 or 2. The cross-judge scored Candidate A 10/12 and Candidate B 5/12, and recommended A after closing coverage gaps. Candidate A was tightened to hash the visible prefix, restrict evidence to that prefix, and require checkpoint-scoped fact labels.

## Implementation contract

```text
ThreadCase = { id, messages: Ordered[ThreadMessage], checkpoints: Ordered[Checkpoint] }
ThreadMessage = { id, sender, subject, body }
Checkpoint = { id, through_message_id, expected_relevance, expected_facts, absent_fact_texts, prohibited_disclosures }
EvidenceRef = { message_id, quote }
ThreadOutput = { case_id, checkpoint_id, input_message_ids, input_sha256, content: JSON({ relevance, facts: [{text, evidence: [EvidenceRef]}] }) }
```

Checkpoint messages are the complete chronological prefix through `through_message_id`. The retained output records exact prefix message IDs and a canonical SHA-256 of those messages. A reviewed fact label is exact `(text, evidence references)` with explicit evidence support and checkpoint-scoped expected fact IDs. Every output string is privacy scanned against the checkpoint's prohibited values and detector. Evidence quotes must occur in the named message within the visible prefix. An explicit message ID disambiguates repeated quotes. Every expected checkpoint and its complete message prefix must occur exactly once. Every current emitted fact must be reviewed as one of that checkpoint's expected facts, so a stale fact without a current label fails as unreviewed.

The scorer's source-grounded checks verify the retained prefix binding and evidence, but do not establish reproducibility of nondeterministic model generation. The runner writes the actual loaded prefix IDs, its hash, and the raw output for each checkpoint. Process and system memory values are cumulative high-water samples for a single server process across initialization, warmup, and all repeated checkpoints. They are not per-run or per-checkpoint samples.

## Throughput and ownership

Blocking gates are the existing fixture schema, model lock, prompt, output scorer, and offline local runtime. Fixture cases, adjudications, runner, scorer, results, and progress record share IDs and one schema, so the project instruction to use one engineer applies. Product inference remains disabled. No Gmail credentials or connector are used.

## Verification result

The pinned model produced the same output file hash in all five runs. All 3/3 thread cases and 6/6 checkpoints passed each run, with zero runner errors. The deterministic verifier rejected all nine controls for missing or reordered coverage, a wrong prefix, future evidence, unreviewed or unsupported facts, recovery-code disclosure, duplicate credit, and a stale deadline. Python compilation and `git diff --check` passed. Case-level results and cumulative memory readings are recorded in `.audit/model-quality-trials/ternary-bonsai-2-27b-mlx-threads/`.
